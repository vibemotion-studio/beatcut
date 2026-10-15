#!/usr/bin/env python3
"""make_reel: turn several clips into a beat-synced reel (colorize reveal, whip-spins, captions, BGM, finale).

    python3 make_reel.py a.mp4 b.mp4 c.mp4 -o out/reel.mp4 --preset datihua
    python3 make_reel.py clip.mp4 --title "Title" --caption bloom:Text@brk --effect glitch@52-68:beat:0.6
    python3 make_reel.py --list
    python3 make_reel.py --clean-cache -o out/reel.mp4

Requires Python 3.9+, numpy, scipy, moderngl, Pillow, opencv, ffmpeg and ffprobe (edge-tts for voiceover).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from reel import catalog, fonts, media, spec as spec_mod  # noqa: E402
from reel.audio import TTS_ENGINES  # noqa: E402
from reel.effects import LOOKS  # noqa: E402
from reel.spec import SECTION_IDS  # noqa: E402

PRESETS = HERE.parent / "presets"
GB = 1024 ** 3


def load_spec(preset_or_path):
    p = Path(preset_or_path).expanduser()
    if not p.exists():
        p = PRESETS / f"{preset_or_path}.json"
    if not p.exists():
        names = sorted(f.stem for f in PRESETS.glob("*.json"))
        sys.exit(f"Preset or spec file not found: {preset_or_path} (presets: {', '.join(names) or 'none'})")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"{p} is not valid JSON: {e}")


def parse_voiceover(value, key="text"):
    """'line@section' -> {key: line, at: section}; without a known section id the whole value is the line or path."""
    body, _, at = value.rpartition("@")
    if body and at in SECTION_IDS:
        return {key: body, "at": at}
    return {key: value}


def parse_size(text):
    try:
        w, h = (int(v) for v in text.lower().split("x"))
    except ValueError:
        sys.exit("--size expects WxH, for example 1080x1920")
    if w < 64 or h < 64:
        sys.exit("--size must be at least 64x64")
    return w - w % 2, h - h % 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", type=Path, help="source video clips (their order is the reel's clip order)")
    ap.add_argument("-o", "--output", type=Path, default=Path("out/reel.mp4"))
    ap.add_argument("--preset", help="preset name from presets/ or a spec JSON path")
    ap.add_argument("--title", help="big centred title")
    ap.add_argument("--subtitle", help="small line under the title")
    ap.add_argument("--caption", action="append", default=[], metavar="LAYOUT:TEXT@SECTION[+OFF][/DUR]")
    ap.add_argument("--effect", action="append", default=[], metavar="NAME[@FROM-TO][:MODE][:AMT]")
    ap.add_argument("--voiceover", action="append", default=[], metavar="TEXT[@SECTION]",
                    help="spoken line (see --tts); without @SECTION lines play one after another")
    ap.add_argument("--voiceover-file", action="append", default=[], metavar="FILE[@SECTION]",
                    help="a recorded voiceover audio file; no subtitle unless the spec JSON also gives its text")
    ap.add_argument("--voice", help="TTS voice name (edge default zh-CN-YunxiNeural, say default Ting-Ting)")
    ap.add_argument("--tts", choices=TTS_ENGINES,
                    help="voiceover engine: edge (Microsoft online, any OS), say (macOS), auto = edge then say (default)")
    ap.add_argument("--no-voice-subtitles", action="store_true", help="do not print voiceover lines as subtitles")
    ap.add_argument("--look", choices=sorted(LOOKS),
                    help="colour grade: neutral (default) or night (warm, stronger glow; for fire and night scenes)")
    ap.add_argument("--typeface", choices=fonts.TYPEFACES, help="serif (default) or sans for every title and caption")
    ap.add_argument("--transition", help="two-sided transition used at quick cuts (see --list)")
    ap.add_argument("--bgm", help="'synth' (default), 'none', or a path to a music file (looped and trimmed)")
    ap.add_argument("--bpm", type=float)
    ap.add_argument("--beats", type=int, help="length in beats (96 beats at 152 bpm = 37.9 s)")
    ap.add_argument("--size", default="1080x1920", help="output WxH (default 1080x1920; use 540x960 for a fast preview)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crf", type=int, default=17)
    ap.add_argument("--params", type=Path, help="JSON file of render engine parameters (keys: DEFAULT in scripts/reel/engine.py)")
    ap.add_argument("--max-clip-seconds", type=float, help="decode at most this many seconds of each clip (saves disk)")
    ap.add_argument("--max-source-edge", type=int,
                    help="long edge in pixels the clips are decoded at (default: the output's long edge; raise it for sharper crops)")
    ap.add_argument("--work-dir", type=Path, help="cache for decoded clips (default: .reel-cache next to the output)")
    ap.add_argument("--clean-cache", action="store_true",
                    help="delete the decoded-clip cache in the work dir and exit (touches nothing else)")
    ap.add_argument("--font-serif", help="override the serif font: path or path:index")
    ap.add_argument("--font-sans", help="override the sans font: path or path:index")
    ap.add_argument("--list", action="store_true", help="print the effect, transition, caption and section catalog")
    args = ap.parse_args()

    if args.list:
        print(catalog.describe())
        return
    if args.clean_cache:
        work = args.work_dir or args.output.parent / ".reel-cache"
        print(f"Removed {media.clean_cache(work) / GB:.2f} GB of decoded-clip cache from {work}")
        return
    if not args.inputs:
        ap.error("give at least one input clip (or use --list)")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")
    if args.fps <= 0:
        ap.error("--fps must be positive")
    if args.max_clip_seconds is not None and args.max_clip_seconds <= 0:
        ap.error("--max-clip-seconds must be positive")
    if args.max_source_edge is not None and args.max_source_edge < 64:
        ap.error("--max-source-edge must be at least 64")

    spec = load_spec(args.preset) if args.preset else {}
    spec = {**spec}
    for key in ("title", "subtitle", "transition", "bgm", "bpm", "beats", "voice", "tts", "look", "typeface"):
        v = getattr(args, key)
        if v is not None:
            spec[key] = v
    if args.no_voice_subtitles:
        spec["voice_subtitles"] = False
    try:
        spec["captions"] = list(spec.get("captions", [])) + [spec_mod.parse_caption(c) for c in args.caption]
        spec["effects"] = list(spec.get("effects", [])) + [spec_mod.parse_effect(e) for e in args.effect]
        spec["voiceover"] = (list(spec.get("voiceover", [])) + [parse_voiceover(v) for v in args.voiceover]
                             + [parse_voiceover(f, "file") for f in args.voiceover_file])
        spec_mod.normalize(spec)
    except ValueError as e:
        sys.exit(f"Invalid spec: {e}")

    if args.font_serif:
        fonts.set_override("serif", args.font_serif)
    if args.font_sans:
        fonts.set_override("sans", args.font_sans)

    from reel.render import render_reel  # imported late: it pulls in OpenGL

    try:
        res = render_reel([str(p) for p in args.inputs], args.output, spec, size=parse_size(args.size), fps=args.fps,
                          crf=args.crf, params_file=args.params, work_dir=args.work_dir,
                          max_long=args.max_source_edge, max_clip_seconds=args.max_clip_seconds,
                          log=lambda m: print(m, flush=True))
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(f"Error: {e}")

    ok = all(c[1] for c in res["checks"])
    for name, passed, detail in res["checks"]:
        print(f"CHECK {'ok  ' if passed else 'FAIL'} {name}: {detail}")
    print(f"VALIDATION={'PASS' if ok else 'FAIL'}")
    print(f"OUTPUT_VIDEO={res['path']}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
