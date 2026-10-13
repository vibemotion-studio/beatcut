"""Reel renderer: clips + spec -> MP4 with video, BGM, footage audio, voiceover, effects and captions."""
import json
import math
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.io import wavfile

from . import audio, bgm, checks
from .engine import DEFAULT, Renderer, encoder
from .effects import EFFECTS, Grade, bright, effect_env, punch_env, radial_glow, rgb_split, sat, whip_frame
from .layouts import blurfill, crop_v, triptych
from .media import Clip
from .plan import build_plan
from .sparks import Shower, composite
from .spec import normalize
from .synth import SR
from .text import Caption, TitleCard
from .timing import sections, smooth
from .transitions import TRANSITIONS

ASSETS = Path(__file__).resolve().parents[2] / "assets"


def effect_params(extra=None, path=None):
    """Render engine parameters: engine defaults, then the night-scene tuning, then file, then extra."""
    p = dict(DEFAULT)
    p.update(json.loads((ASSETS / "params_night.json").read_text()))
    if path:
        p.update(json.loads(Path(path).read_text()))
    p.update(extra or {})
    bad = sorted(set(p) - set(DEFAULT))
    if bad:
        raise ValueError(f"unknown effect parameters {bad}; allowed: {sorted(DEFAULT)}")
    return {k: float(v) for k, v in p.items()}


def _base_frame(ctx, s, st, lf):
    """Lay out the shot's source frame on the canvas. Updates the per-shot state (play position, trail)."""
    W, H = ctx.W, ctx.H
    lt = lf / ctx.fps
    u = lf / max(1, s["n"] - 1)
    kind = s["kind"]
    if kind == "bridge":
        return ctx.last_base.copy() if ctx.last_base is not None else np.zeros((H, W, 3), np.uint8)
    clip = ctx.clips[s["clip"]]
    pos = float(s["f0"]) if kind == "hold" else st["pos"]
    fidx = int(round(min(max(pos, 0), len(clip) - 1)))
    if kind == "finale":
        img = crop_v(clip.sample(pos), clip.track()[fidx], 1.0 + 0.06 * u, W, H)
        st["pos"] = pos + s["speed"]
        lay = ctx.shower.layer(lt)
        ctx.energy.append(float(lay.mean()))
        return composite(img, lay, 0.55 - 0.35 * smooth(lt / max(0.5, 0.9 * s["n"] / ctx.fps)))
    src = clip.sample(pos)
    if s.get("trail"):
        sf = src.astype(np.float32)
        st["trail"] = sf if st["trail"] is None else np.maximum(sf, st["trail"] * s["trail"])
        src = st["trail"].astype(np.uint8)
    if kind == "tri":
        img = triptych(clip, pos, s["offsets"], W, H)
    else:
        z = s["zoom"](lt) if callable(s.get("zoom")) else s.get("zoom", 1.0)
        if kind == "hold":
            z *= 1 + s.get("push", 0) * u
        pe = 0.0
        if s.get("punch"):
            pe = punch_env(lt, s["punch"][0])
            z *= 1 + (s["punch"][1] - 1) * pe
        img = blurfill(src, W, H) if s["layout"] == "blur" else crop_v(src, clip.track()[fidx], z, W, H)
        if pe > 0:
            img = sat(img, 1 + 0.35 * pe)
    if kind in ("play", "tri"):
        st["pos"] = pos + s.get("speed", 1.0)
    return img


def _user_effects(img, effects, tg, lt, dur, beat):
    for e in effects:
        if e["from"] * beat <= tg < e["to"] * beat:
            amt = e["amt"] * effect_env(e["mode"], tg, lt, dur, beat)
            if amt > 0.02:
                img = EFFECTS[e["name"]][0](img, amt, tg)
    return img


def _plan_voices(spec, sec_t, work, total_s, log):
    """Synthesize every voiceover line and place it on the timeline. Returns [(audio, t)]."""
    out, cursor = [], 0.4
    for v in spec["voiceover"]:
        arr = audio.synthesize_voice(v["text"], spec["voice"], work)
        at = v["at"]
        base = cursor if at is None else (sec_t[at] if isinstance(at, str) else float(at))
        t = max(0.0, base + v["offset"])
        dur = len(arr) / SR
        if t + dur > total_s:
            log(f"Warning: voiceover '{v['text'][:16]}...' ends at {t + dur:.1f}s, past the {total_s:.1f}s video")
        out.append((arr, t))
        cursor = t + dur + 0.3
    return out


def render_reel(clip_paths, out_path, spec=None, size=(1080, 1920), fps=30, crf=17, params_file=None,
                work_dir=None, src_size=(1920, 1080), log=print):
    """Render a reel. Returns dict(path, seconds, frames, checks=[(name, ok, detail)])."""
    spec = normalize(spec)
    if not clip_paths:
        raise ValueError("need at least one input clip")
    W, H = size
    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(work_dir).expanduser() if work_dir else out.parent / ".reel-cache"
    work.mkdir(parents=True, exist_ok=True)

    clips = [Clip(p, work, fps, src_size) for p in clip_paths]
    nb, bpm = spec["beats"], spec["bpm"]
    beat = 60.0 / bpm
    shots = build_plan(clips, nb, bpm, fps, spec["transition"])
    starts, acc = [], 0
    for s in shots:
        starts.append(acc)
        acc += s["n"]
    total = acc
    total_s = total / fps
    secs = sections(nb)
    sec_t = {sid: b0 * beat for sid, _, b0, _ in secs}
    log(f"{len(clips)} clip(s) -> {len(shots)} shots, {total} frames = {total_s:.2f}s at {bpm:g} bpm / {nb} beats")

    voices = _plan_voices(spec, sec_t, work, total_s, log)
    overlays = []
    if spec["title"]:
        overlays.append(TitleCard(spec["title"], spec["subtitle"], W, 0.10, min(3.0, max(0.5, secs[0][3] * beat - 0.1))))
    for c in spec["captions"]:
        t0 = (c["beat"] * beat if c["beat"] is not None else sec_t[c["at"]]) + c["offset"]
        overlays.append(Caption(c["layout"], c["text"], t0, c["dur"], c["tag"], beat))
    if spec["voice_subtitles"]:
        overlays += [Caption("subtitle", v["text"], t, len(a) / SR) for v, (a, t) in zip(spec["voiceover"], voices)]

    params = effect_params(spec["params"], params_file)
    rnd = Renderer(W, H)
    grade = Grade(W, H)
    burst_map = radial_glow(W, H)
    px = W / 1080.0
    fade_n = min(38, max(6, total // 6))
    ctx = SimpleNamespace(clips=clips, W=W, H=H, fps=fps, last_base=None, shower=None, energy=[])
    silent = work / "reel_silent.mp4"
    enc = encoder(str(silent), W, H, fps, crf, None)
    si, st = -1, {}
    try:
        for gi in range(total):
            while si + 1 < len(shots) and gi >= starts[si + 1]:
                si += 1
                s = shots[si]
                st = dict(trail=None, pos=float(s.get("f0", 0)))
                if s["kind"] == "finale":
                    ctx.shower = Shower(beat, s["b1"] - s["b0"], W, H)
            s = shots[si]
            lf = gi - starts[si]
            tg, lt, dur = gi / fps, lf / fps, s["n"] / fps
            u = lf / max(1, s["n"] - 1)
            img = _base_frame(ctx, s, st, lf)
            prev = ctx.last_base
            if lf == s["n"] - 1:
                ctx.last_base = img.copy()
            if s.get("trans") and prev is not None and lf < s["trans"][1]:
                name, nf = s["trans"]
                img = TRANSITIONS[name][0](prev, img, (lf + 1) / (nf + 1))
            if s.get("q"):
                rnd.set_frame(img)
                img = np.ascontiguousarray(rnd.render(s["q"](lt), params))
            if s.get("burst"):
                sb = (u ** 3) * 0.7
                img = np.clip(img.astype(np.float32) * (1 - sb) + 255.0 * sb * burst_map, 0, 255).astype(np.uint8)
            img = _user_effects(img, spec["effects"], tg, lt, dur, beat)
            if s.get("pulse"):
                amp = math.exp(-(tg % beat) / 0.07)
                img = bright(rgb_split(img, 16 * px * amp), 0.10 * amp)
            if s.get("whip") and lf < 5:
                img = whip_frame(img, lf)
            if si + 1 < len(shots) and shots[si + 1].get("whip") and starts[si + 1] - gi <= 5:
                img = whip_frame(img, gi - starts[si + 1])
            img = grade(img)
            for o in overlays:
                img = o.draw(img, tg)
            if gi < 20:
                a = 0.55 * math.exp(-tg / 0.3)
                img = np.clip(img.astype(np.float32) * (1 - a) + 255 * a, 0, 255).astype(np.uint8)
            if gi >= total - fade_n:
                img = (img.astype(np.float32) * (1 - (gi - (total - fade_n) + 1) / fade_n)).astype(np.uint8)
            enc.stdin.write(np.ascontiguousarray(img).tobytes())
            if gi % 100 == 0:
                log(f"frame {gi}/{total} shot={s['name']}")
        enc.stdin.close()
    except BaseException:
        enc.kill()
        raise
    if enc.wait():
        raise RuntimeError("ffmpeg failed while encoding the video")

    log("mixing audio")
    n_samples = int(round(total_s * SR))
    if spec["bgm"] == "synth":
        music = bgm.render(nb, bpm, spec["seed"])
    elif spec["bgm"] == "none":
        music = None
    else:
        music = audio.load_music(Path(spec["bgm"]).expanduser(), n_samples)
    events = []
    for s, t0 in zip(shots, starts):
        clip = clips[s["clip"]] if "clip" in s else None
        if not s.get("audio") or s["kind"] != "play" or clip is None or not clip.has_audio:
            continue
        sp = s.get("speed", 1.0)
        a0 = s["f0"] / fps
        arr = clip.audio(a0, min(a0 + s["n"] / fps * sp, clip.duration), sp)
        if len(arr):
            events.append((arr, t0 / fps, s["audio"]))
    whips = [t0 / fps for s, t0 in zip(shots, starts) if s.get("whip")]
    fin = next((t0 / fps for s, t0 in zip(shots, starts) if s["kind"] == "finale"), None)
    crackle = (ctx.energy, fin, fps) if fin is not None and ctx.energy else None
    mix = audio.mix_reel(total_s, music, events, whips, crackle, voices, spec["duck"], spec["seed"])
    wav = work / "reel_audio.wav"
    wavfile.write(str(wav), SR, (mix * 32767).astype(np.int16))
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg mux failed: {r.stderr.strip()[-300:]}")
    res = checks.validate(out, W, H, total_s, True, continuous_audio=music is not None)
    return dict(path=out, seconds=total_s, frames=total, checks=res)
