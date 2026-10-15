"""Checks that run before any slow work, so a bad path, font, voice file or full disk fails in seconds."""
import shutil
from pathlib import Path

from . import audio, fonts, media

GB = 1024 ** 3


def run(clip_paths, spec, work, fps, max_long, max_seconds):
    """Validate every input. Raises FileNotFoundError, ValueError or RuntimeError with an actionable message.

    Returns the bytes the decoded clip caches can need (upper bound, ignoring caches that already exist).
    """
    need = 0
    for p in clip_paths:
        path = Path(p).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"input clip not found: {path}")
        info = media.probe(path)
        if not info["video"]:
            raise ValueError(f"no video stream in {path}")
        need += media.estimate_bytes(info, fps, max_long, max_seconds)

    if spec["bgm"] not in ("synth", "none"):
        music = Path(spec["bgm"]).expanduser()
        if not music.exists():
            raise FileNotFoundError(f"bgm file not found: {music}")
        if not media.probe(music)["audio"]:
            raise ValueError(f"bgm file has no audio stream: {music}")

    needs_tts = False
    for i, v in enumerate(spec["voiceover"]):
        if v["file"]:
            f = Path(v["file"]).expanduser()
            if not f.exists():
                raise FileNotFoundError(f"voiceover[{i}].file not found: {f}")
            if not media.probe(f)["audio"]:
                raise ValueError(f"voiceover[{i}].file has no audio stream: {f}")
        else:
            needs_tts = True
    if needs_tts:
        audio.resolve_engine(spec["tts"])

    fonts.check()

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    extra = max(0, need - media.cache_bytes(work))
    free = shutil.disk_usage(work).free
    if extra > free:
        raise RuntimeError(f"decoding the clips needs about {extra / GB:.1f} GB in {work} but only {free / GB:.1f} GB "
                           f"is free; lower --max-clip-seconds or --max-source-edge, or pick another --work-dir")
    return need
