---
name: beatcut
description: Turn several video clips into a beat-synced vertical reel built on the colorize engine (黑白到彩色上色 + 丁达尔旋焦). Adds whip-spin cuts, a spin-through bridge, a time-slice triptych, a synthesized 152 bpm BGM that never stops, flat-white titles and captions, optional voiceover with music ducking, 剪映-style effects (色差/故障/抖动/闪白/VHS/镜像/马赛克...) and transitions (叠化/推移/拉近/快速横移/擦除...), and a procedural falling-spark finale. Use when users ask for 卡点视频, 踩点混剪, 竖屏混剪, 多段视频合成一条, 打铁花视频, 旅行记录混剪, 上色转场合集, 给视频加配音/字幕/BGM/特效/转场, beat-synced reel, montage, or want colorize applied across several clips with titles, music and effects. Outputs H.264 MP4, 1080x1920 by default.
---

# Beatcut

The render engine (black-and-white to color reveal with Tyndall spin focus) is `scripts/reel/engine.py`, derived from vibe-motion/colorize. That tool gives one reveal per clip; this skill plans a whole reel on a beat grid.

## Workflow

1. Collect the clips as absolute paths. Their order is the clip order: the first clip opens the reel, the last one is used for the finale.
2. Ask what title and captions are wanted. If there are none, render without `--title` and `--caption`, or start from `presets/datihua.json` and say that its captions are written for iron-fireworks footage.
3. Resolve the skill directory and install dependencies once (see Quick Start).
4. Render a quick preview first: `--size 540x960 --beats 24 --crf 23`.
5. Render the full reel. Wait for `VALIDATION=PASS` and `OUTPUT_VIDEO=<absolute path>`.
6. Report the output path and the settings used. `VALIDATION` is numeric only (size, duration, audio, clipping, music never silent). It does not judge how the video looks. Extract frames with `ffmpeg -ss T -i out.mp4 -frames:v 1 f.png` and look at them if you can; if you cannot view images, say so instead of claiming the look was checked.

## Quick Start

```bash
skill_dir=""
for base in "${AGENTS_HOME:-$HOME/.agents}" "${CLAUDE_HOME:-$HOME/.claude}" "${CODEX_HOME:-$HOME/.codex}"; do
  if [ -d "$base/skills/beatcut" ]; then
    skill_dir="$base/skills/beatcut"
    break
  fi
done
[ -n "$skill_dir" ] || { echo "beatcut skill not found under ~/.agents, ~/.claude, or ~/.codex"; exit 1; }

python3 -m pip install -r "$skill_dir/scripts/requirements.txt"
python3 "$skill_dir/scripts/make_reel.py" /abs/a.mp4 /abs/b.mp4 -o "$(pwd)/out/reel.mp4" --title "标题" --subtitle "SUBTITLE"
```

If the agent already knows the directory containing this `SKILL.md`, use that as `skill_dir`. `python3 make_reel.py --list` prints every effect, transition, caption layout and section id.

## Common Commands

```bash
# Preview (fast)
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 c.mp4 -o out/p.mp4 --size 540x960 --beats 24 --crf 23

# The iron-fireworks preset, 96 beats = 37.9 s
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 c.mp4 d.mp4 -o out/reel.mp4 --preset datihua

# Own title, one caption, one effect, a transition at the quick cuts
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 -o out/r.mp4 --title "上海" --subtitle "SHANG HAI" \
  --caption "bloom:外滩@brk+0.2/1.5" --effect "glitch@52-68:beat:0.6" --transition whip

# Voiceover over the music (edge-tts by default, --tts say on macOS); lines without @section play one after another
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 -o out/v.mp4 --voiceover "这是第一句@s2" --voiceover "这是第二句"

# A recorded voiceover, a warm night grade and one sans family for every title
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 -o out/n.mp4 --voiceover-file /abs/narration.wav@s2 --look night --typeface sans

# Free the decoded-clip cache (it can reach several GB)
python3 "$skill_dir/scripts/make_reel.py" --clean-cache -o out/reel.mp4

# Your own music instead of the synthesized BGM (looped and trimmed to the video length)
python3 "$skill_dir/scripts/make_reel.py" a.mp4 b.mp4 -o out/m.mp4 --bgm /abs/music.mp3
```

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `inputs` | required | Source video clips, 1 or more. |
| `-o, --output` | `out/reel.mp4` | Output MP4 path. |
| `--preset` | none | Preset name from `presets/` or a spec JSON path. Flags below override it. |
| `--title`, `--subtitle` | none | Big centred title and the small line under it. |
| `--caption` | none | `layout:text@section[+offset][/dur]`, repeatable. |
| `--effect` | none | `name[@from-to][:mode][:amt]`, repeatable. `from-to` are beats. |
| `--voiceover` | none | `text[@section]`, repeatable. Spoken by the TTS engine and shown as a subtitle. |
| `--voiceover-file` | none | `file[@section]`, repeatable. A recorded voiceover; no subtitle unless the spec JSON also gives its `text`. |
| `--tts` | `auto` | `edge` (Microsoft online, any OS; the text is sent to Microsoft's service), `say` (macOS, local) or `auto` (edge, then say). |
| `--voice` | engine default | TTS voice name. Defaults: `zh-CN-YunxiNeural` (edge), `Ting-Ting` (say). |
| `--look` | `neutral` | `neutral`, or `night` for fire and night scenes (warm grade, stronger glow). The `datihua` preset uses `night`. |
| `--typeface` | `serif` | `serif` or `sans`: one family for every title and caption. |
| `--no-voice-subtitles` | off | Do not print voiceover lines as subtitles. |
| `--transition` | none | Two-sided transition used at the quick cuts, the second reveal and the triptych. |
| `--bgm` | `synth` | `synth`, `none`, or a music file path. |
| `--bpm`, `--beats` | `152`, `96` | Tempo and length. `--beats` must be at least 10; sections scale with it. |
| `--size` | `1080x1920` | Output WxH. |
| `--fps`, `--crf` | `30`, `17` | Frame rate and x264 quality. Use crf 20-22 for files you will share. |
| `--params` | none | JSON file of render engine parameters; the keys are `DEFAULT` in `scripts/reel/engine.py`. |
| `--max-clip-seconds` | full clip | Decode at most this many seconds of each clip (saves disk). |
| `--max-source-edge` | output long edge | Long edge in pixels the clips are decoded at. Raise it for sharper tall crops. |
| `--work-dir` | `.reel-cache` next to output | Cache for decoded clips. |
| `--clean-cache` | off | Delete the decoded-clip cache in the work dir and exit. Touches nothing else. |
| `--font-serif`, `--font-sans` | system | Font override: `path` or `path:index`. |

## Spec JSON

Presets and `--preset file.json` use the same keys as the flags:

```json
{
  "title": "打铁花", "subtitle": "IRON FIREWORKS",
  "bpm": 152, "beats": 96, "bgm": "synth", "transition": "whip",
  "captions": [{"layout": "bloom", "text": "铁水成花", "tag": "MOLTEN IRON", "at": "brk", "offset": 0.0, "dur": 1.55}],
  "effects": [{"name": "glitch", "from": 52, "to": 68, "mode": "beat", "amt": 0.6}],
  "voiceover": [{"text": "第一句", "at": "s2"}, {"file": "narration.wav", "text": "字幕文字", "at": "chill"}],
  "tts": "auto", "voice": "zh-CN-YunxiNeural", "look": "neutral", "typeface": "serif", "duck": 0.5
}
```

A caption needs `at` (a section id) or `beat`. `offset` and `dur` are seconds. A voiceover entry needs `text` (spoken by the TTS engine and shown as a subtitle) or `file` (a recorded audio file; add `text` as well to get a subtitle). Its `at` is a section id or a number of seconds; leave it out to follow the previous line. Two lines that would overlap are rejected. Unknown keys and bad values are rejected with a message.

## Sections

Boundaries are in beats of a 96-beat canon and scale with `--beats`.

| id | beats | What plays |
| --- | --- | --- |
| `intro` | 0-8 | White flash, hold on clip 1, colorize reveal, big title |
| `s2` | 8-20 | Half-speed play with light trails |
| `groove1` | 20-32 | Quick plays of 4 beats, the last punches in with a whip-spin |
| `brk` | 32-36 | Zoomed hold |
| `groove2` | 36-44 | The last quick play continues |
| `bridge` | 44-46 | Spin-through bridge ending in a light burst |
| `chill` | 46-52 | Second colorize reveal |
| `peak` | 52-68 | One cut per beat with a pulse on every beat |
| `ramp` | 68-72 | Time-slice triptych |
| `fin` | 72-96 | Falling-spark finale over slowed footage, then fade to black |

## Effects, transitions, captions

`--list` prints the full table. Effects: `rgb_split shake flash glitch zoom_pulse mirror mosaic grain vhs letterbox radial_blur motion_blur strobe invert blur ripple mono`. Effect modes: `always beat start end ramp`. Transitions: `fade slide zoom whip glitch flash wipe spin mosaic`. Caption layouts: `ignite bloom focus meteors grand subtitle`.

## Style rules

Text is flat white with wide letter-spacing, a soft drop shadow only, and one warm accent on thin rules. One serif family for Chinese (or one sans family with `--typeface sans`), a light sans for small English tags. Captions differ by position, layout and entrance, not by font or effect. Do not add calligraphy fonts, gold gradients, thick outlines, glows or seals: they were tried and read as dated. Details and the measured reference are in `references/style-guide.md`.

## Behavior

- Before any slow work, preflight checks the clips, the BGM file, voiceover files, the TTS engine, the fonts and the free disk space, so a bad input fails in seconds.
- Source clips are decoded once, in their own aspect ratio, with the long edge capped at the output's long edge (`--max-source-edge`), at the output fps, and cached under the work dir. A 30 s 1080p clip costs about 5.6 GB; `--max-clip-seconds` and `--clean-cache` keep it down.
- When a shot needs more frames than its clip has, the planner moves the start earlier or, for a continued shot, warns that the last frame will hold.
- Quick plays pick the brightest spark windows of each clip and keep the action centred in the tall crop by tracking bright pixels.
- The synthesized BGM is D major pentatonic. A drone and a pad run from the first to the last sample, so it is never silent. Every cut sits on its beat grid.
- Footage audio is mixed under the music with 30 ms fades. Voiceover ducks music and footage by `duck`.
- The mix is soft-limited to a 0.89 peak and fades out at the end.
- Output checks: size, duration, audio present, no clipped samples (the mix is clipped before it is written as 16-bit, so no sample can wrap), and no quiet 0.25 s window when music is on.

## Requirements

- Python 3.9+ with `numpy`, `scipy`, `moderngl`, `Pillow`, `opencv-python-headless`, `edge-tts` (`scripts/requirements.txt`)
- `ffmpeg` and `ffprobe` on `PATH`
- OpenGL 3.3 (the render engine)
- Internet access for `edge-tts` voiceover (it sends the spoken text to Microsoft's service); `--tts say` (macOS) and `--voiceover-file` stay local.
- macOS for the default fonts (Songti SC, PingFang SC). Elsewhere set `REEL_FONT_SERIF` and `REEL_FONT_SANS` to a CJK font; this path is untested.

Tests: `python3 -m pytest tests` from the skill directory (unit tests plus a synthetic-clip end-to-end run).
