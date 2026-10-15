"""Source clips: decoded once into a cached uint8 array, with per-frame scores, a centroid track and audio."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

from .synth import SR

_CACHE_FILE = re.compile(r"^[0-9a-f]{16}\.(u8|part)$")


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def probe(path):
    """{'video': bool, 'audio': bool, 'width', 'height' (as displayed, rotation applied), 'duration'}."""
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "stream=codec_type,width,height:stream_tags=rotate:stream_side_data=rotation:format=duration",
              "-of", "json", str(path)], text=True)
    if r.returncode:
        raise ValueError(f"ffprobe failed for {path}: {r.stderr.strip()[-300:]}")
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    out = {"video": v is not None, "audio": any(s.get("codec_type") == "audio" for s in streams),
           "width": 0, "height": 0, "duration": float(info.get("format", {}).get("duration") or 0)}
    if v:
        w, h = v["width"], v["height"]
        rot = v.get("tags", {}).get("rotate") or next(
            (d["rotation"] for d in v.get("side_data_list", []) if "rotation" in d), 0)
        if abs(round(float(rot))) % 180 == 90:
            w, h = h, w
        out.update(width=w, height=h)
    return out


def decode_size(w, h, max_long):
    """Source size scaled down (never up) so the long side is at most max_long, both sides even."""
    s = min(1.0, max_long / max(w, h))
    return max(2, int(round(w * s / 2)) * 2), max(2, int(round(h * s / 2)) * 2)


def estimate_bytes(info, fps=30, max_long=1920, max_seconds=None):
    """Disk the decoded cache of one probed clip (see probe) will take."""
    w, h = decode_size(info["width"], info["height"], max_long)
    secs = min(info["duration"], max_seconds) if max_seconds else info["duration"]
    return int(secs * fps) * w * h * 3


def _cache_files(work_dir):
    work = Path(work_dir)
    if not work.is_dir():
        return []
    return [p for p in work.iterdir() if p.is_file() and _CACHE_FILE.match(p.name)]


def cache_bytes(work_dir):
    """Bytes the decoded-frame caches in work_dir already use."""
    return sum(p.stat().st_size for p in _cache_files(work_dir))


def clean_cache(work_dir):
    """Delete decoded-frame caches (<16 hex>.u8 / .part) in work_dir and return the bytes freed. Touches nothing else."""
    freed = 0
    for p in _cache_files(work_dir):
        freed += p.stat().st_size
        p.unlink()
    return freed


class Clip:
    """A source video decoded at ``fps`` in its own aspect ratio, long side at most ``max_long``; frames are a read-only memmap."""

    def __init__(self, path, work_dir, fps=30, max_long=1920, max_seconds=None):
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        info = probe(self.path)
        if not info["video"]:
            raise ValueError(f"no video stream in {self.path}")
        self.has_audio = info["audio"]
        self.fps = fps
        self.w, self.h = decode_size(info["width"], info["height"], max_long)
        st = self.path.stat()
        key = f"{self.path}|{st.st_mtime_ns}|{st.st_size}|{fps}|{(self.w, self.h)}"
        if max_seconds:
            key += f"|{max_seconds}"
        key = hashlib.sha1(key.encode()).hexdigest()[:16]
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        raw = work / f"{key}.u8"
        if not raw.exists():
            tmp = work / f"{key}.part"
            cmd = ["ffmpeg", "-y", "-v", "error"] + (["-t", str(max_seconds)] if max_seconds else []) + [
                "-i", str(self.path), "-vf", f"fps={fps},scale={self.w}:{self.h}", "-an",
                "-f", "rawvideo", "-pix_fmt", "rgb24", str(tmp)]
            r = _run(cmd)
            if r.returncode:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"ffmpeg decode failed for {self.path}: {r.stderr.decode()[-300:]}")
            tmp.rename(raw)
        n = raw.stat().st_size // (self.w * self.h * 3)
        if n < 2:
            raise ValueError(f"no frames decoded from {self.path}")
        self.frames = np.memmap(raw, np.uint8, "r", shape=(n, self.h, self.w, 3))
        self._scores = None
        self._track = None

    def __len__(self):
        return len(self.frames)

    @property
    def duration(self):
        return len(self) / self.fps

    def sample(self, f):
        """Frame at fractional index f (clamped), linearly blended between neighbours."""
        n = len(self)
        f = min(max(f, 0.0), n - 1.0)
        i = int(f)
        a = f - i
        if a < 0.02 or i >= n - 1:
            return np.ascontiguousarray(self.frames[i])
        return cv2.addWeighted(np.ascontiguousarray(self.frames[i]), 1 - a,
                               np.ascontiguousarray(self.frames[i + 1]), a, 0)

    def scores(self):
        """Per-frame spark score: percent of near-white pixels plus twice the percent of saturated warm ones."""
        if self._scores is None:
            out = np.zeros(len(self))
            for i in range(len(self)):
                s = cv2.resize(np.ascontiguousarray(self.frames[i]), (240, 135), interpolation=cv2.INTER_AREA)
                hsv = cv2.cvtColor(s, cv2.COLOR_RGB2HSV)
                gray = cv2.cvtColor(s, cv2.COLOR_RGB2GRAY)
                hot = ((hsv[..., 0] < 25) | (hsv[..., 0] > 165)) & (hsv[..., 1] > 90) & (hsv[..., 2] > 180)
                out[i] = (gray > 230).mean() * 100 + 2 * hot.mean() * 100
            self._scores = out
        return self._scores

    def windows(self, length=12, k=3):
        """Start frames of up to k non-overlapping windows of ``length`` frames, brightest first."""
        n = len(self)
        if n <= length:
            return [0]
        cs = np.convolve(self.scores(), np.ones(length) / length, mode="valid")
        out = []
        for i in np.argsort(cs)[::-1]:
            if all(abs(int(i) - j) >= length for j in out):
                out.append(int(i))
            if len(out) == k:
                break
        return out

    def track(self):
        """Smoothed horizontal centroid (0..1) of the brightest pixels, used to keep the action in a tall crop."""
        if self._track is None:
            n = len(self)
            xs = np.full(n, np.nan)
            for i in range(n):
                g = cv2.cvtColor(np.ascontiguousarray(self.frames[i][::8, ::8]), cv2.COLOR_RGB2GRAY).astype(np.float32)
                w = np.clip(g - 190, 0, None)
                if w.sum() > 60:
                    xs[i] = (w.sum(0) * np.arange(g.shape[1])).sum() / w.sum() / g.shape[1]
            last = 0.5
            for i in range(n):
                if np.isnan(xs[i]):
                    xs[i] = last
                else:
                    last = xs[i]
            self._track = gaussian_filter1d(xs, 5, mode="nearest")
        return self._track

    def audio(self, t0, t1, tempo=1.0):
        """Stereo float32 audio for source seconds [t0, t1), 30 ms fades. Empty if there is none or tempo is out of range."""
        if not self.has_audio or t1 <= t0 or not 0.5 <= tempo <= 2.0:
            return np.zeros((0, 2), np.float32)
        af = f"atrim=start={t0:.4f}:end={t1:.4f},asetpts=PTS-STARTPTS"
        if abs(tempo - 1.0) > 1e-6:
            af += f",atempo={tempo}"
        r = _run(["ffmpeg", "-v", "error", "-i", str(self.path), "-vn", "-af", af, "-ac", "2", "-ar", str(SR),
                  "-f", "f32le", "-"])
        if r.returncode:
            raise RuntimeError(f"ffmpeg audio extract failed for {self.path}: {r.stderr.decode()[-300:]}")
        a = np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()
        fd = int(0.03 * SR)
        if len(a) > 2 * fd:
            a[:fd] *= np.linspace(0, 1, fd)[:, None]
            a[-fd:] *= np.linspace(1, 0, fd)[:, None]
        return a
