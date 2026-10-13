"""Render engine: black-and-white to color reveal with Tyndall spin focus.

Four GLSL passes (color sweep, horizontal motion blur x2, spin blur with a focus disc, glow) driven
per frame by Renderer.render(q), where q in [0, 1] is the reveal progress (q=0 is full mono plus
max spin). encoder() opens an ffmpeg pipe that takes raw RGB frames.

Derived from the renderer in vibe-motion/colorize (scripts/colorize.py), reduced to the renderer and
encoder. That repository ships no license file, so check its terms before redistributing.
"""
from pathlib import Path
import subprocess
import numpy as np
import moderngl
from PIL import Image

MAPS = Path(__file__).resolve().parents[2]/'assets/effect_maps'

VERT = '''#version 330
in vec2 pos; out vec2 uv;
void main(){uv=pos*.5+.5;gl_Position=vec4(pos,0,1);}
'''
COMMON = '''#version 330
in vec2 uv; out vec4 frag;
uniform sampler2D src;
vec3 lut(sampler2D tex, vec3 c){
 c=clamp(c,0.,1.);float b=c.b*63.;
 vec2 q0=vec2(mod(floor(b),8.),floor(floor(b)/8.));
 vec2 q1=vec2(mod(ceil(b),8.),floor(ceil(b)/8.));
 vec2 p0=q0*.125+vec2(.5/512.)+(.125-1./512.)*c.rg;
 vec2 p1=q1*.125+vec2(.5/512.)+(.125-1./512.)*c.rg;
 return mix(texture(tex,p0).rgb,texture(tex,p1).rgb,fract(b));
}
'''
# Monochrome-to-color sweep with a soft, depth-like front.
GRAD = COMMON + '''
uniform sampler2D monoLut, colorLut;
uniform float edge, front, depth0, depthY, depthR, grade;
void main(){
 vec3 c=texture(src,uv).rgb;
 vec3 color=mix(c,lut(colorLut,c),grade);
 vec3 mono=lut(monoLut,c);
 float d=.75*uv.x+depth0+depthY*(uv.y-.5)+depthR*length(uv-.5);
 float m=1.-smoothstep(front-edge,front+edge,d);
 frag=vec4(mix(mono,color,m),1);
}
'''
# Horizontal motion blur; two passes are stacked per frame.
MOTION = COMMON + '''
uniform float stepUV, count, alpha;
uniform sampler2D original;
void main(){
 vec3 s=texture(src,uv).rgb;float n=1.;
 for(int i=1;i<=11;i++){
  if(float(i)>count)break;
  for(int side=-1;side<=1;side+=2){
   vec2 p=uv+vec2(float(i*side)*stepUV,0);
   if(p.x>=0.&&p.x<=1.){s+=texture(src,p).rgb;n+=1.;}
  }
 }
 frag=vec4(mix(texture(original,uv).rgb,s/n,alpha),1);
}
'''
ROTATE = COMMON + '''
uniform sampler2D focusMask;
uniform float angle, aspect, focusScale, centerX, centerY;
void main(){
 vec3 s=vec3(0);float n=0.;vec2 center=vec2(centerX,centerY);
 vec2 p=(uv-center)*vec2(aspect,1);
 for(int i=0;i<33;i++){
  // One-sided arc from 0 to angle. A centered kernel would cancel the
  // angular displacement and lose the visible turning motion.
  float a=angle*float(i)/32.;float cs=cos(a),sn=sin(a);
  vec2 q=vec2(cs*p.x-sn*p.y,sn*p.x+cs*p.y)/vec2(aspect,1)+center;
  if(all(greaterThanEqual(q,vec2(0)))&&all(lessThanEqual(q,vec2(1)))){s+=texture(src,q).rgb;n+=1.;}
 }
 // The focus disc is a square focusScale*max(w,h) wide at the frame center,
 // used as a luma matte for the unrotated layer. Its scale grows from zero,
 // so the sharp area spreads outward from the center.
 vec2 d=(uv-.5)*vec2(aspect,1)/max(aspect,1.);
 float keep=focusScale>0.?dot(texture(focusMask,.5+d/focusScale).rgb,vec3(.299,.587,.114)):0.;
 frag=vec4(mix(s/max(n,1.),texture(src,uv).rgb,keep),1);
}
'''
GLOW = COMMON + '''
uniform sampler2D tyndallLut;
uniform float bloom, radius, threshold, gain, gammaVal, lift, grade, softness, saturation, rays;
uniform vec2 resolution;
void main(){
 vec3 c=texture(src,uv).rgb;
 vec3 b=vec3(0);float n=0.;
 for(int y=-3;y<=3;y++)for(int x=-3;x<=3;x++){
  float w=exp(-float(x*x+y*y)/5.);
  vec3 a=texture(src,uv+vec2(x,y)*radius/resolution).rgb;
  float l=max(max(a.r,a.g),a.b);
  b+=a*smoothstep(threshold,1.,l)*w;n+=w;
 }
 vec3 ray=vec3(0);float rn=0.;
 for(int i=0;i<24;i++){
  float f=float(i)/23.;float w=exp(-f*1.);
  vec3 a=texture(src,mix(uv,vec2(.9,.92),f*.26)).rgb;
  ray+=a*smoothstep(.75,1.,max(max(a.r,a.g),a.b))*w;rn+=w;
 }
 vec3 soft=vec3(0);float sn=0.;
 for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++){
  float w=(x==0?2.:1.)*(y==0?2.:1.);
  soft+=texture(src,uv+vec2(x,y)*softness/resolution).rgb*w;sn+=w;
 }
 c=soft/sn;
 c=1.-(1.-c)*(1.-b/n*bloom-ray/rn*rays);
 c=mix(c,lut(tyndallLut,c),grade);
 c=mix(vec3(dot(c,vec3(.299,.587,.114))),c,saturation);
 c=pow(max(c,vec3(0)),vec3(gammaVal))*gain+lift;
 frag=vec4(clamp(c,0.,1.),1);
}
'''

# Fitted against Jianying exports of 单彩渐变 + 动感模糊 + 丁达尔旋焦 on static
# photos. Temporal values are interpolated, so any duration and fps work.
DEFAULT = dict(depth0=.144148, depthY=.052029, depthR=-.163598, edge=.236978,
               front_speed=.631164, front_start=-.35, grade=.1, angle=.050265,
               focus_scale=.9, motion=.700743, motion_range=.982808, bloom=.536758,
               radius=5., threshold=.5, gain=.952346, gamma=.981704, lift=0.,
               tyndall_grade=.437028, center_x=.5, center_y=.5, softness=2.307218,
               saturation=.982107, rays=.285462, blur_power=.995649, bloom_start=.298435)


class Renderer:
    def __init__(self, width, height):
        self.w, self.h = width, height
        try:
            self.ctx = moderngl.create_standalone_context(require=330)
        except Exception:
            # Headless Linux has no default GL context; EGL usually works there.
            self.ctx = moderngl.create_standalone_context(require=330, backend='egl')
        self.vbo = self.ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32).tobytes())
        self.programs, self.vaos = {}, {}
        for k, s in [('grad', GRAD), ('motion', MOTION), ('rotate', ROTATE), ('glow', GLOW)]:
            p = self.ctx.program(vertex_shader=VERT, fragment_shader=s)
            self.programs[k] = p
            self.vaos[k] = self.ctx.simple_vertex_array(p, self.vbo, 'pos')
        self.buffers = [self.ctx.texture((width, height), 3, dtype='f2') for _ in range(5)]
        self.fbos = [self.ctx.framebuffer(color_attachments=[t]) for t in self.buffers]
        self.maps = {}
        for key, file in [('monoLut', 'mono_lut.png'), ('colorLut', 'color_lut.png'),
                          ('tyndallLut', 'tyndall_lut.png'), ('focusMask', 'focus_mask.png')]:
            # LUT and mask rows stay in file order: they are texture
            # coordinates, not display coordinates.
            a = np.asarray(Image.open(MAPS/file).convert('RGB'))
            self.maps[key] = self.ctx.texture((a.shape[1], a.shape[0]), 3, a.tobytes())
        self.input = self.ctx.texture((width, height), 3)
        for tex in [*self.maps.values(), *self.buffers, self.input]:
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            tex.repeat_x = tex.repeat_y = False

    def set_frame(self, rgb):
        self.input.write(np.ascontiguousarray(rgb[::-1]).tobytes())

    def run(self, name, out, textures, values):
        p = self.programs[name]
        for i, (key, tex) in enumerate(textures.items()):
            if key in p:
                tex.use(i)
                p[key].value = i
        for key, value in values.items():
            if key in p:
                p[key].value = value
        self.fbos[out].use()
        self.ctx.viewport = (0, 0, self.w, self.h)
        self.vaos[name].render(moderngl.TRIANGLE_STRIP)
        return self.buffers[out]

    def render(self, q, p):
        """Render the current frame at reveal progress q in [0, 1]."""
        decay = 1-q
        scale = min(self.w, self.h)/1080
        g = self.run('grad', 0, {'src': self.input, **self.maps},
                     {**p, 'front': p['front_start']+2*q*p['front_speed']})
        # Two horizontal sampling passes: 70/100 displacement, 85 -> 0 strength.
        m = self.run('motion', 1, {'src': g, 'original': g},
                     dict(stepUV=2/720*(40/7)*p['motion_range'], count=8., alpha=1.))
        m = self.run('motion', 2, {'src': m, 'original': g},
                     dict(stepUV=2/720*p['motion_range'], count=7., alpha=p['motion']*decay))
        # Spin blur 40 -> 0 shortens the arc while atmosphere 0 -> 30 grows
        # the focus disc, so the frame settles from the center outward.
        r = self.run('rotate', 3, {'src': m, 'focusMask': self.maps['focusMask']},
                     dict(angle=p['angle']*decay**p['blur_power'], aspect=self.w/self.h,
                          focusScale=p['focus_scale']*q, centerX=p['center_x'], centerY=p['center_y']))
        glow = p['bloom_start']+(1-p['bloom_start'])*q
        self.run('glow', 4, {'src': r, **self.maps},
                 dict(bloom=p['bloom']*glow, radius=p['radius']*scale, threshold=p['threshold'],
                      gain=p['gain'], gammaVal=p['gamma'], lift=p['lift'], grade=p['tyndall_grade'],
                      resolution=(self.w, self.h), softness=p['softness']*scale,
                      saturation=p['saturation'], rays=p['rays']*glow))
        a = np.frombuffer(self.fbos[4].read(components=3, alignment=1), np.uint8)
        return a.reshape(self.h, self.w, 3)[::-1]


def encoder(path, w, h, fps, crf, audio=None, audio_length=None):
    """audio: None, 'silent', or a media path whose first audio stream is kept."""
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', f'{w}x{h}', '-r', str(fps), '-i', '-']
    if audio == 'silent':
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    elif audio:
        cmd += (['-t', str(audio_length)] if audio_length else []) + ['-i', str(audio)]
    cmd += ['-map', '0:v:0']
    if audio:
        # apad + shortest: the clip always ends with the last video frame.
        cmd += ['-map', '1:a:0', '-af', 'apad', '-c:a', 'aac', '-b:a', '192k',
                '-ar', '48000', '-ac', '2', '-shortest']
    cmd += ['-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', str(crf), '-movflags', '+faststart',
            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
