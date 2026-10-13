"""Audio helpers: voiceover (macOS `say`), external music, BGM ducking and the final mix."""
import hashlib
import shutil
import subprocess
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d

from . import synth
from .synth import SR


def decode(path):
    """Any audio/video file -> stereo float32 array at 48 kHz (empty array if it has no audio)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg could not decode {path}: {r.stderr.decode()[-300:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def voice_available():
    return shutil.which("say") is not None


def synthesize_voice(text, voice, work_dir):
    """Speak ``text`` with the macOS `say` voice and return stereo float32 audio. Cached by text and voice."""
    if not text.strip():
        raise ValueError("voiceover text is empty")
    if not voice_available():
        raise RuntimeError("macOS `say` was not found; voiceover needs macOS (or drop the voiceover entries)")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:12]
    aiff, txt = work / f"vo_{key}.aiff", work / f"vo_{key}.txt"
    if not aiff.exists():
        txt.write_text(text, encoding="utf-8")   # via file so the text can never be read as a command-line flag
        r = subprocess.run(["say", "-v", voice, "-f", str(txt), "-o", str(aiff)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"say failed with voice '{voice}': {r.stderr.strip()[-200:]}")
    arr = decode(aiff)
    if len(arr) == 0:
        raise RuntimeError(f"say produced no audio for voice '{voice}'")
    return arr


def load_music(path, n_samples, fade_s=1.1):
    """Decode a music file, loop or trim it to n_samples, fade the end, and cap the peak at 0.89."""
    a = decode(path)
    if len(a) == 0:
        raise ValueError(f"no audio in {path}")
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
