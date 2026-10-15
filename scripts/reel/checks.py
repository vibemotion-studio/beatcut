"""Numeric output checks. Reports measurements only; it never claims anything about how the video looks."""
import json
import subprocess

import cv2
import numpy as np


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffprobe failed for {path}: {r.stderr.strip()[-200:]}")
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise ValueError(f"no video stream in {path}")
    return dict(width=v["width"], height=v["height"], duration=float(j.get("format", {}).get("duration") or 0),
                audio=any(s.get("codec_type") == "audio" for s in j["streams"]))


def video_curve(path):
    """Per-second mean brightness, saturation and frame-difference motion."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    rows, prev, i = [], None, 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        s = cv2.resize(fr, (135, 240))
        hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
        g = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY).astype(np.float32)
        rows.append((i / fps, hsv[..., 2].mean(), hsv[..., 1].mean(), 0.0 if prev is None else np.abs(g - prev).mean()))
        prev = g
        i += 1
    cap.release()
    r = np.array(rows) if rows else np.zeros((0, 4))
    out = []
    for sec in range(int(r[-1, 0]) + 1 if len(r) else 0):
        m = (r[:, 0] >= sec) & (r[:, 0] < sec + 1)
        out.append((sec, float(r[m, 1].mean()), float(r[m, 2].mean()), float(r[m, 3].mean())))
    return out


def audio_stats(path, win_s=0.25):
    """Peak, saturated-sample count, quietest window rms and the number of windows under 0.02 rms (48 kHz mono).

    Sample-to-sample jumps are deliberately not judged: a crash cymbal and a click look the same to that metric.
    """
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg could not read the audio of {path}: {r.stderr.decode()[-200:]}")
    a = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768
    if len(a) < 2:
        return None
    w = int(48000 * win_s)
    rms = np.array([np.sqrt((a[i:i + w] ** 2).mean()) for i in range(0, max(1, len(a) - w), w)])
    return dict(peak=float(np.abs(a).max()), clipped=int((np.abs(a) > 0.999).sum()), min_rms=float(rms.min()),
                quiet_windows=int((rms < 0.02).sum()))


def validate(path, width, height, expect_s, expect_audio, continuous_audio=False):
    """List of (name, ok, detail) checks against the expected size, duration and audio."""
    p = probe(path)
    res = [("size", (p["width"], p["height"]) == (width, height), f"{p['width']}x{p['height']} (want {width}x{height})"),
           ("duration", abs(p["duration"] - expect_s) <= 0.15, f"{p['duration']:.2f}s (want {expect_s:.2f}s)"),
           ("audio", p["audio"] == expect_audio, f"audio={p['audio']} (want {expect_audio})")]
    if p["audio"]:
        st = audio_stats(path)
        if st:
            res.append(("no clipping", st["clipped"] == 0, f"{st['clipped']} clipped samples, peak {st['peak']:.3f}"))
            if continuous_audio:
                res.append(("music never silent", st["quiet_windows"] == 0,
                            f"{st['quiet_windows']} windows under 0.02 rms, quietest {st['min_rms']:.4f}"))
    return res
