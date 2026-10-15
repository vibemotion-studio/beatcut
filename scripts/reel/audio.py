"""Audio helpers: voiceover (edge-tts, macOS `say` or a local file), external music, BGM ducking and the final mix."""
import asyncio
import hashlib
import importlib.util
import shutil
import subprocess
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

from . import synth
from .media import probe
from .synth import SR

TTS_ENGINES = ("auto", "edge", "say")
DEFAULT_VOICE = {"edge": "zh-CN-YunxiNeural", "say": "Ting-Ting"}
VOICE_RMS = 0.14


def decode(path):
    """Any audio/video file -> stereo float32 array at 48 kHz. Raises ValueError if it has no audio stream."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)
    if not probe(p)["audio"]:
        raise ValueError(f"no audio stream in {p}")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg could not decode {p}: {r.stderr.decode()[-300:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def edge_available():
    return importlib.util.find_spec("edge_tts") is not None


def say_available():
    return shutil.which("say") is not None


def resolve_engine(tts="auto"):
    """'auto' prefers edge-tts (any OS, online) and falls back to macOS `say`. Raises with an actionable message."""
    if tts not in TTS_ENGINES:
        raise ValueError(f"tts must be one of {TTS_ENGINES}, got {tts!r}")
    if tts == "auto":
        for name, ok in (("edge", edge_available()), ("say", say_available())):
            if ok:
                return name
        raise RuntimeError("no voiceover engine: `pip install edge-tts==7.3.1` (online), run on macOS for `say`, "
                           "or give voiceover entries a local 'file'")
    if tts == "edge" and not edge_available():
        raise RuntimeError("edge-tts is not installed: `pip install edge-tts==7.3.1`")
    if tts == "say" and not say_available():
        raise RuntimeError("macOS `say` was not found; use --tts edge or give voiceover entries a local 'file'")
    return tts


def _say(text, voice, out):
    txt = out.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")   # via file so the text can never be read as a command-line flag
    r = subprocess.run(["say", "-v", voice, "-f", str(txt), "-o", str(out)], capture_output=True, text=True)
    if r.returncode:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"say failed with voice '{voice}': {r.stderr.strip()[-200:]}")


def _edge(text, voice, out):
    import edge_tts

    async def go(dest):
        await edge_tts.Communicate(text, voice).save(str(dest))

    tmp = out.with_name(out.name + ".part")
    try:
        asyncio.run(go(tmp))
    except Exception as e:   # network, unknown voice, empty audio: all surface as one clear error
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"edge-tts failed for voice '{voice}': {e}. It needs internet access to Microsoft's "
                           f"service; list voices with `edge-tts --list-voices`") from e
    tmp.rename(out)


def synthesize_voice(text, voice, work_dir, tts="auto"):
    """Speak ``text`` and return stereo float32 audio at 48 kHz. Cached by engine, voice and text.

    edge-tts sends the text to Microsoft's online service; macOS `say` stays on the machine.
    """
    if not text.strip():
        raise ValueError("voiceover text is empty")
    engine = resolve_engine(tts)
    voice = voice or DEFAULT_VOICE[engine]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{engine}|{voice}|{text}".encode()).hexdigest()[:12]
    out = work / f"vo_{key}.{'mp3' if engine == 'edge' else 'aiff'}"
    if not out.exists():
        (_edge if engine == "edge" else _say)(text, voice, out)
    return decode(out)


def prepare_voice(arr, rms_target=VOICE_RMS):
    """Trim leading and trailing silence (keeping 40 ms / 60 ms) and set a common loudness, so any engine mixes alike."""
    m = np.abs(arr).max(1) if len(arr) else np.zeros(0)
    if len(m) == 0 or m.max() < 1e-4:
        raise ValueError("voiceover audio is silent")
    act = np.nonzero(m > 0.04 * m.max())[0]
    a = arr[max(0, act[0] - int(0.04 * SR)):min(len(arr), act[-1] + int(0.06 * SR))].copy()
    fd = min(int(0.008 * SR), len(a) // 2)
    if fd > 0:
        a[:fd] *= np.linspace(0, 1, fd)[:, None]
        a[-fd:] *= np.linspace(1, 0, fd)[:, None]
    a *= rms_target / max(float(np.sqrt((a ** 2).mean())), 1e-9)
    return a * min(1.0, 0.9 / float(np.abs(a).max()))


def load_music(path, n_samples, fade_s=1.1):
    """Decode a music file, loop or trim it to n_samples, fade the end, and cap the peak at 0.89."""
    a = decode(path)
    if len(a) == 0:
        raise ValueError(f"no audio samples in {path}")
    a = np.tile(a, (int(np.ceil(n_samples / len(a))), 1))[:n_samples].copy()
    fd = min(int(fade_s * SR), len(a))
    if fd > 0:
        a[-fd:] *= np.linspace(1, 0, fd)[:, None]
    return a * min(1.0, 0.89 / (np.abs(a).max() + 1e-9))


def duck_curve(n, spans, depth=0.5, attack=0.12, release=0.35):
    """Gain curve over n samples that dips by ``depth`` inside each (t0, t1) span, with smoothed edges."""
    g = np.ones(n, np.float32)
    for t0, t1 in spans:
        i0, i1 = max(0, int(t0 * SR)), min(n, int(t1 * SR))
        if i1 > i0:
            g[i0:i1] = 1.0 - depth
    size = max(1, int((attack + release) / 2 * SR))
    return uniform_filter1d(g, size=size, mode="nearest").astype(np.float32)


def _put(buf, sig, t, gain=1.0):
    if sig.ndim == 1:
        sig = np.repeat(sig[:, None], 2, axis=1)
    i = int(round(t * SR))
    if i >= len(buf) or i + len(sig) <= 0:
        return
    a, e = max(0, -i), min(len(sig), len(buf) - i)
    buf[i + a:i + e] += sig[a:e] * gain


def mix_reel(total_s, bgm, clip_events, whips, crackle, voices, depth=0.5, seed=3):
    """Final stereo mix.

    bgm: (n, 2) array or None.  clip_events: [(audio, t, gain)] source-footage audio.
    whips: [t] whoosh times.  crackle: (energy list, t0, fps) or None.  voices: [(audio, t)].
    The music and footage are ducked by ``depth`` while a voice line plays.
    """
    synth.reseed(seed)
    N = int(round(total_s * SR))
    music = np.zeros((N, 2), np.float32)
    if bgm is not None and len(bgm):
        m = min(N, len(bgm))
        music[:m] = bgm[:m] * 0.9
    foot = np.zeros((N, 2), np.float32)
    for arr, t, g in clip_events:
        _put(foot, arr, t, g)
    fx = np.zeros((N, 2), np.float32)
    for t in whips:
        _put(fx, synth.whoosh(0.45), t - 0.2, 0.30)
    if crackle is not None:
        energy, t0, fps = crackle
        en = np.asarray(energy, np.float32)
        en = en / (en.max() + 1e-9)
        r = np.random.default_rng(seed)
        for k, v in enumerate(en):
            for _ in range(r.poisson(5 * float(v))):
                _put(fx, synth.click(), t0 + (k + r.uniform(0, 1)) / fps, 0.12 * r.uniform(0.5, 1.0))
    vo = np.zeros((N, 2), np.float32)
    for arr, t in voices:
        _put(vo, arr, t, 1.0)
    duck = np.ones(N, np.float32)
    if voices and depth > 0:
        duck = duck_curve(N, [(t, t + len(a) / SR) for a, t in voices], depth)
    out = (music + foot) * duck[:, None] + fx + vo
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    out *= 0.89 / (np.abs(out).max() + 1e-9)
    fd = min(N, int(0.3 * SR))
    out[-fd:] *= np.linspace(1, 0, fd)[:, None]
    return out.astype(np.float32)
