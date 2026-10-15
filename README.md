<div align="center">

# beatcut

**Beat-synced vertical reels from your own clips.**

Colorize reveal · whip-spin cuts · BGM that never stops · captions · voiceover · 17 effects · 9 transitions · a falling-spark finale

[English](README.md) | [简体中文](README_CN.md)

<img src="assets/demo.gif" alt="beatcut demo: title and colorize reveal, one cut per beat, falling-spark finale" width="216" />

<sub>Excerpts of a 37.9 s render on iron-fireworks footage: opening reveal, beat cuts, finale.</sub>

</div>

**beatcut** is an agent skill and a command-line tool. Give it several video clips and it plans the whole reel on a beat grid, renders it at 1080×1920, and mixes music, footage audio, voiceover and sound effects into one MP4. It builds on the [colorize](https://github.com/vibe-motion/colorize) engine (black-and-white to color reveal with Tyndall spin focus).

## Highlights

- **Planned on the beat.** The default reel is 96 beats at 152 bpm (37.9 s). Every cut lands on a beat, and the plan scales to any length of 10 beats or more.
- **A real structure.** Flash opening with a colorize reveal, half-speed light trails, quick plays, a spin-through bridge, a second reveal, one cut per beat, a time-slice triptych, then a falling-spark finale.
- **Music that never stops.** A synthesized D-major BGM runs from the first to the last sample, or bring your own track.
- **Flat white typography.** Six caption layouts that differ by position and entrance, never by font or glow.
- **CapCut-style toolbox.** 17 effects and 9 transitions you can place on beats or over a range of beats.
- **Voiceover that behaves.** Speak lines with edge-tts (any OS, online) or macOS `say`, or bring a recorded file. Voices duck the music and footage audio and appear as subtitles.
- **Fails early, checks honestly.** Inputs, fonts and voice files are verified before the slow render starts, and each run ends with numeric checks on size, duration, clipping and silence.

## Quick start

Install as an agent skill, or run it from the command line.

```bash
git clone https://github.com/vibemotion-studio/beatcut.git
cd beatcut
python3 -m pip install -r scripts/requirements.txt

# Claude Code (or ~/.codex/skills, ~/.agents/skills)
ln -s "$(pwd)" ~/.claude/skills/beatcut
```

Needs Python 3.9+, `ffmpeg` and `ffprobe` on `PATH`, and an OpenGL 3.3 driver. Voiceover through `edge-tts` needs internet access and sends the spoken text to Microsoft's service; `--tts say` and `--voiceover-file` stay on your machine.

Then ask your agent:

| You say | It does |
| --- | --- |
| "Make a beat-synced reel from these clips: /abs/a.mp4 /abs/b.mp4" | Renders a 540×960 preview first, then the full 1080×1920 reel |
| "Add the title 'Shanghai' and a lower-left caption 'The Bund'" | `--title`, `--caption bloom:The Bund@brk` |
| "Put a glitch on every beat in the middle section" | `--effect glitch@52-68:beat` |
| "Use this music instead" | `--bgm /abs/music.mp3`, looped and trimmed to fit |
| "Add a voiceover" | `--voiceover`, with ducking and subtitles |

## Command line

```bash
# Fast preview
python3 scripts/make_reel.py a.mp4 b.mp4 c.mp4 -o out/p.mp4 --size 540x960 --beats 24 --crf 23

# Iron-fireworks preset (its captions are written for that footage)
python3 scripts/make_reel.py a.mp4 b.mp4 c.mp4 d.mp4 -o out/reel.mp4 --preset datihua

# Own title, caption, effect, transition and voiceover
python3 scripts/make_reel.py a.mp4 b.mp4 -o out/r.mp4 --title "Shanghai" --subtitle "SHANG HAI" \
  --caption "bloom:The Bund@brk+0.2/1.5" --effect "glitch@52-68:beat:0.6" --transition whip \
  --voiceover "First line@s2"

# Warm night grade, one sans family, a recorded voiceover
python3 scripts/make_reel.py a.mp4 b.mp4 -o out/n.mp4 --look night --typeface sans --voiceover-file narration.wav@s2

# Free the decoded-clip cache (it can reach several GB)
python3 scripts/make_reel.py --clean-cache -o out/reel.mp4

python3 scripts/make_reel.py --list     # every effect, transition, layout and section id
```

The run ends with `VALIDATION=PASS` and `OUTPUT_VIDEO=<path>`. All options are listed in [SKILL.md](SKILL.md).

## How a reel is planned

Sections are measured in beats of a 96-beat canon and scale with `--beats`. Clips are used in the order you pass them: the first opens the reel and the last carries the finale.

| Section | Beats | What plays |
| --- | --- | --- |
| `intro` | 0-8 | White flash, hold on clip 1, colorize reveal, big title |
| `s2` | 8-20 | Half-speed play with light trails |
| `groove1` | 20-32 | Quick plays of 4 beats; the last punches in with a whip-spin |
| `brk` | 32-36 | Zoomed hold |
| `groove2` | 36-44 | The last quick play continues |
| `bridge` | 44-46 | Spin-through bridge ending in a light burst |
| `chill` | 46-52 | Second colorize reveal |
| `peak` | 52-68 | One cut per beat with a pulse on every beat |
| `ramp` | 68-72 | Time-slice triptych |
| `fin` | 72-96 | Falling-spark finale over slowed footage, then fade to black |

## Effects, transitions, captions

| Effects | |
| --- | --- |
| `rgb_split` `shake` `flash` `glitch` `zoom_pulse` `mirror` | 色差 抖动 闪白 故障 心跳 镜像 |
| `mosaic` `grain` `vhs` `letterbox` `radial_blur` `motion_blur` | 马赛克 胶片颗粒 复古VHS 电影黑边 变焦模糊 动感模糊 |
| `strobe` `invert` `blur` `ripple` `mono` | 频闪 反色 模糊 水波纹 黑白 |

Effect modes: `always` `beat` `start` `end` `ramp`. Syntax: `--effect name[@from-to][:mode][:amt]`, where `from-to` are beats.

**Transitions:** `fade` `slide` `zoom` `whip` `glitch` `flash` `wipe` `spin` `mosaic`, applied at the quick cuts, the second reveal and the triptych.

**Caption layouts:** `ignite` (vertical column) · `bloom` (lower-left lines) · `focus` (top, tracking contracts) · `meteors` (diagonal cascade) · `grand` (bottom, one character per beat) · `subtitle` (voiceover lines). Syntax: `--caption layout:text@section[+offset][/dur]`.

## Spec file

Presets and `--preset file.json` use the same keys as the flags:

```json
{
  "title": "打铁花", "subtitle": "IRON FIREWORKS",
  "bpm": 152, "beats": 96, "bgm": "synth", "transition": "whip",
  "captions": [{"layout": "bloom", "text": "铁水成花", "tag": "MOLTEN IRON", "at": "brk", "dur": 1.55}],
  "effects": [{"name": "glitch", "from": 52, "to": 68, "mode": "beat", "amt": 0.6}],
  "voiceover": [{"text": "First line", "at": "s2"}, {"file": "narration.wav", "text": "Shown as subtitle", "at": "chill"}],
  "tts": "auto", "voice": "zh-CN-YunxiNeural", "look": "neutral", "typeface": "serif", "duck": 0.5
}
```

A voiceover entry needs `text` (spoken by the TTS engine and shown as a subtitle) or `file` (a recorded audio file; add `text` as well to get a subtitle). Two lines that would overlap are rejected. Unknown keys and bad values are rejected with a message.

## Checks

`VALIDATION` is numeric only: output size, duration, audio track, clipped samples, and (with music on) any quiet 0.25 s window. It does not judge how the video looks, so watch the result yourself. The caption style rules and the reel they were measured from are in [references/style-guide.md](references/style-guide.md).

## Repository layout

```text
beatcut/
├── SKILL.md                 # agent entry point: workflow, options, sections
├── presets/datihua.json     # iron-fireworks preset
├── references/style-guide.md
├── assets/                  # effect maps, engine parameters, demo GIF
├── agents/openai.yaml
├── scripts/
│   ├── make_reel.py         # command-line entry
│   └── reel/                # engine, plan, render, media, layouts, effects, transitions,
│                            # text, sparks, bgm, synth, audio, spec, checks, fonts
└── tests/                   # unit tests + an end-to-end run on synthetic clips
```

## Limits

- The default fonts (Songti SC, PingFang SC) and `--tts say` need macOS. Elsewhere set `REEL_FONT_SERIF` and `REEL_FONT_SANS` to a CJK font (untested); edge-tts voiceover works on any OS with internet access.
- Clips are decoded in their own aspect ratio, long edge capped at the output's long edge, and cached on disk (a 30 s 1080p clip is about 5.6 GB). Use `--max-clip-seconds`, `--max-source-edge` and `--clean-cache` to control it.
- The default look is `neutral`; the `datihua` preset switches to `night` (warm grade, stronger glow).
- Caption layouts are designed for 1080×1920 and scale to other sizes; not every size was checked.
- The `datihua` preset and the demo GIF use iron-fireworks footage.

## Notices

- The render passes in `scripts/reel/engine.py` are derived from [vibe-motion/colorize](https://github.com/vibe-motion/colorize), which ships no license file. Check its terms before redistributing.
- The color lookup tables and focus mask in `assets/effect_maps/` come from the Jianying (CapCut) effect pack and are for study and research only. Check the licensing yourself before redistributing.

## Tests

```bash
python3 -m pytest tests
```
