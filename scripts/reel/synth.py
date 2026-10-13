"""Synth voices and a tiny stereo bus. numpy/scipy only, deterministic given reseed()."""
import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
_rng = np.random.default_rng(11)


def reseed(seed):
    global _rng
    _rng = np.random.default_rng(seed)


def rng():
    return _rng


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(n):
    return np.arange(n) / SR


def _noise(n):
    return _rng.standard_normal(n)


def filt(kind, f, x):
    w = [v / (SR / 2) for v in f] if isinstance(f, (list, tuple)) else f / (SR / 2)
    return np.asarray(sosfilt(butter(2, w, kind, output="sos"), x))


def norm(x):
    return x / (np.abs(x).max() + 1e-9)


# ------------------------------------------------------------------ drums and fx
def kick(dur=0.5):
    n = int(dur * SR)
    t = _t(n)
    ph = 2 * np.pi * np.cumsum(45 + 120 * np.exp(-t * 30)) / SR
    body = np.sin(ph) * np.exp(-t * 7) * (1 - np.exp(-t * 900))
    return body + filt("low", 3500, _noise(n)) * np.exp(-t * 400) * 0.25


def taiko(dur=1.3):
    n = int(dur * SR)
    t = _t(n)
    ph = 2 * np.pi * np.cumsum(62 + 95 * np.exp(-t * 16)) / SR
    body = np.sin(ph) * np.exp(-t * 3.4) * (1 - np.exp(-t * 700))
    return body + filt("band", [140, 900], _noise(n)) * np.exp(-t * 13) * 0.45


def clap():
    n = int(0.3 * SR)
    t = _t(n)
    y = np.zeros(n)
    for off, a in ((0.0, 1.0), (0.011, 0.8), (0.022, 0.7)):
        i = int(off * SR)
        y[i:] += a * filt("band", [1100, 5500], _noise(n - i)) * np.exp(-_t(n - i) * 60)
    y += filt("band", [900, 3500], _noise(n)) * np.exp(-t * 14) * 0.5
    return y * 0.8


def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    return filt("high", 7000, _noise(n)) * np.exp(-_t(n) * (18 if open_ else 90))


def crash(dur=2.4):
    n = int(dur * SR)
    t = _t(n)
    return filt("high", 3500, _noise(n)) * np.exp(-t * 2.2) * (1 - np.exp(-t * 800)) * 0.7


def boom(dur=0.6, f0=130, f1=40, k=14):
    t = _t(int(dur * SR))
    ph = 2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-t * k)) / SR
    return np.sin(ph) * np.exp(-t * 6) * (1 - np.exp(-t * 600))


def riser(dur):
    n = int(dur * SR)
    u = np.linspace(0, 1, n)
    tone = np.sin(2 * np.pi * np.cumsum(150 + 2000 * u ** 2) / SR)
    return (filt("high", 700, _noise(n)) * 0.5 + tone * 0.3) * u ** 2.2


def whoosh(dur=0.45):
    n = int(dur * SR)
    x = _noise(n)
    u = np.linspace(0, 1, n)
    sweep = (filt("band", [300, 1200], x) * (1 - u) ** 2 + filt("band", [1200, 4000], x) * np.sin(np.pi * u)
             + filt("band", [4000, 9000], x) * u ** 2)
    return norm(sweep * np.sin(np.pi * u) ** 1.6)


def click():
    n = int(0.012 * SR)
    return np.diff(_noise(n), prepend=0.0) * np.exp(-np.arange(n) / SR * 350)


def tail(dur=1.4):
    n = int(dur * SR)
    return norm(filt("low", 2500, _noise(n)) * np.exp(-_t(n) * 3.2))


# ------------------------------------------------------------------ tonal
def bass(m, dur):
    n = int(dur * SR)
    t = _t(n)
    f = hz(m)
    y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    env = (1 - np.exp(-t * 400)) * np.exp(-np.maximum(t - dur * 0.6, 0) * 14) * (0.6 + 0.4 * np.exp(-t * 8))
    return y * env * 0.6


def pluck(m, dur=1.5):
    n = int(dur * SR)
    t = _t(n)
    f = hz(m)
    y = np.zeros(n)
    for h in range(1, 15):
        fh = f * h * np.sqrt(1 + 2e-4 * h * h)
        if fh > 0.45 * SR:
            break
        y += np.sin(2 * np.pi * fh * t) * np.exp(-t * (1.2 + 1.6 * h)) / h ** 1.1
    y *= 1 - np.exp(-t * 1200)
    k = int(0.004 * SR)
    y[:k] += _noise(k) * 0.03 * np.hanning(k)
    return y / (np.abs(y).max() + 1e-9)


def pad(notes, dur, att=0.45, rel=0.7):
    n = int((dur + rel) * SR)
    t = _t(n)
    env = np.interp(t, [0, att, dur, dur + rel], [0, 1, 1, 0])
    left, right = np.zeros(n), np.zeros(n)
    for m in notes:
        f = hz(m)
        for det, wl, wr in ((0.0032, 1.0, 0.25), (-0.0032, 0.25, 1.0), (0.0, 0.6, 0.6)):
            s = np.zeros(n)
            for h in range(1, 8):
                s += np.sin(2 * np.pi * f * (1 + det) * h * t + 0.7 * h) / h ** 1.6
            left += s * wl
            right += s * wr
    pk = max(np.abs(left).max(), np.abs(right).max()) + 1e-9
    return left / pk * env, right / pk * env


# ------------------------------------------------------------------ bus and reverb
class Bus:
    def __init__(self, n):
        self.l = np.zeros(n)
        self.r = np.zeros(n)

    def _span(self, ln, t):
        i = int(round(t * SR))
        n = len(self.l)
        if i >= n or i + ln <= 0:
            return None
        a = max(0, -i)
        return i, a, min(ln, n - i)

    def add(self, sig, t, gain=1.0, pan=0.0):
        sp = self._span(len(sig), t)
        if sp is None:
            return
        i, a, e = sp
        th = (pan + 1) * np.pi / 4
        s = sig[a:e] * gain
        self.l[i + a:i + e] += s * np.cos(th)
        self.r[i + a:i + e] += s * np.sin(th)

    def addst(self, left, right, t, gain=1.0):
        sp = self._span(len(left), t)
        if sp is None:
            return
        i, a, e = sp
        self.l[i + a:i + e] += left[a:e] * gain
        self.r[i + a:i + e] += right[a:e] * gain


def _ir(seed, dur=1.9):
    g = np.random.default_rng(seed)
    n = int(dur * SR)
    ir = filt("low", 6000, g.standard_normal(n) * np.exp(-_t(n) * 2.4))
    k = int(0.015 * SR)
    ir[:k] *= np.linspace(0, 1, k)
    return ir / np.sqrt((ir ** 2).sum())


_IRL, _IRR = _ir(1), _ir(2)


def verb(bus, n):
    return fftconvolve(bus.l, _IRL)[:n], fftconvolve(bus.r, _IRR)[:n]
