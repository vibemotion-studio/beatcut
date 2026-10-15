"""Flat white typography, as measured on the reference reel: no gradient, outline or glow.

Pure white fill, wide letter-spacing, only a soft drop shadow for legibility over sparks, and one warm
accent colour used on thin rules. Chinese titles use one serif family and small tags use a light sans.
The five caption layouts differ by position, structure and entrance, never by font or effects.
"""
import math
import textwrap
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .fonts import get_font
from .timing import clamp01, ease_out

WHITE = (255, 255, 255)
ACCENT = (255, 176, 64)
_chars = {}


def scale_k(W, H):
    """Design scale: typography is laid out for a 1080x1920 canvas."""
    return min(W / 1080.0, H / 1920.0)


def _shade(ta, size, color):
    """Straight-alpha sprite: flat colour plus a soft drop shadow."""
    sh = np.roll(cv2.GaussianBlur(ta, (0, 0), max(2.0, size * 0.07)), max(1, int(size * 0.03)), axis=0) * 0.5
    a = ta + (1 - ta) * sh
    rgb = np.asarray(color, np.float32)[None, None] * (ta / np.maximum(a, 1e-6))[..., None]
    return rgb, np.clip(a, 0, 1)


def char_sprite(ch, role, size, color=WHITE):
    size = int(size)
    key = (ch, role, size, color)
    if key not in _chars:
        S = size * 2
        m = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m).text((S / 2, S / 2), ch, font=get_font(role, size), fill=255, anchor="mm")
        _chars[key] = _shade(np.asarray(m, np.float32) / 255, size, color)
    return _chars[key]


@lru_cache(maxsize=48)
def run_sprite(text, role, size, track, color=WHITE):
    """One line with letter-spacing ``track`` (in em). The ink starts int(size*0.6) px from the left edge."""
    size = int(size)
    f = get_font(role, size)
    adv = [f.getlength(c) for c in text]
    gap = size * track
    pad = int(size * 0.6)
    cw, ch = int(sum(adv) + gap * (len(text) - 1)) + 2 * pad, int(size * 1.4) + 2 * pad
    m = Image.new("L", (cw, ch), 0)
    d = ImageDraw.Draw(m)
    x = float(pad)
    for c, a in zip(text, adv):
        d.text((x, ch / 2), c, font=f, fill=255, anchor="lm")
        x += a + gap
    return _shade(np.asarray(m, np.float32) / 255, size, color)


def clear_caches():
    """Drop cached glyph and line sprites (call after changing the typeface or a font override)."""
    _chars.clear()
    run_sprite.cache_clear()


def fit_run(text, role, target_w, track, color=WHITE):
    """Sprite whose ink is about target_w px wide."""
    f = get_font(role, 200)
    tw = sum(f.getlength(c) for c in text) + 200 * track * (len(text) - 1)
    return run_sprite(text, role, max(8, int(200 * target_w / tw)), round(track, 3), color)


def wipe(sprite, p, soft=60):
    """Reveal a sprite left to right; p in [0, 1]."""
    rgb, a = sprite
    x = np.arange(a.shape[1], dtype=np.float32)
    return rgb, a * (np.clip(p * (a.shape[1] + soft) - x, 0, soft) / soft)[None, :]


# ---------------------------------------------------------------- primitives
def _mix(img, x0, y0, a, color):
    h, w = a.shape
    sub = img[y0:y0 + h, x0:x0 + w].astype(np.float32)
    img[y0:y0 + h, x0:x0 + w] = np.clip(sub * (1 - a[..., None]) + np.asarray(color, np.float32) * a[..., None],
                                        0, 255).astype(np.uint8)
    return img


def blit(img, rgb, a, cx, cy, ang=0.0, sc=1.0, alpha=1.0):
    """Alpha-composite a sprite centred at (cx, cy), rotated ang degrees counter-clockwise, scaled sc."""
    if alpha <= 0.003 or sc <= 0.01:
        return img
    H, W = img.shape[:2]
    h, w = a.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, sc)
    M[0, 2] += cx - w / 2
    M[1, 2] += cy - h / 2
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], np.float32)
    dst = corners @ M[:, :2].T + M[:, 2]
    x0, y0 = np.floor(dst.min(0)).astype(int)
    x1, y1 = np.ceil(dst.max(0)).astype(int)
    X0, Y0, X1, Y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if X1 <= X0 or Y1 <= Y0:
        return img
    M2 = M.copy()
    M2[0, 2] -= X0
    M2[1, 2] -= Y0
    size = (int(X1 - X0), int(Y1 - Y0))
    rw = cv2.warpAffine(rgb, M2, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                        borderValue=(0, 0, 0))
    aw = cv2.warpAffine(a, M2, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,))
    aa = (aw * alpha)[..., None]
    sub = img[Y0:Y1, X0:X1].astype(np.float32)
    img[Y0:Y1, X0:X1] = np.clip(sub * (1 - aa) + rw * aa, 0, 255).astype(np.uint8)
    return img


def rule(img, p0, p1, width, color, alpha):
    """Thin crisp anti-aliased line, no glow."""
    if alpha <= 0.003 or abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) < 1.5:
        return img
    H, W = img.shape[:2]
    pad = int(width) + 3
    x0, x1 = int(max(min(p0[0], p1[0]) - pad, 0)), int(min(max(p0[0], p1[0]) + pad, W))
    y0, y1 = int(max(min(p0[1], p1[1]) - pad, 0)), int(min(max(p0[1], p1[1]) + pad, H))
    if x1 <= x0 or y1 <= y0:
        return img
    m = np.zeros((y1 - y0, x1 - x0), np.float32)
    cv2.line(m, (int(round(p0[0] - x0)), int(round(p0[1] - y0))),
             (int(round(p1[0] - x0)), int(round(p1[1] - y0))), (1.0,), max(1, int(round(width))), cv2.LINE_AA)
    return _mix(img, x0, y0, m * alpha, color)


def streak(img, x, y, ang_deg, length, width, color, alpha):
    """Thin tail ending at head (x, y), trailing back along -direction(ang_deg); fades and thins to the tail."""
    if alpha <= 0.003 or length < 4:
        return img
    H, W = img.shape[:2]
    ux, uy = math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))
    tx, ty = x - ux * length, y - uy * length
    pad = int(width * 3) + 4
    x0, x1 = int(max(min(x, tx) - pad, 0)), int(min(max(x, tx) + pad, W))
    y0, y1 = int(max(min(y, ty) - pad, 0)), int(min(max(y, ty) + pad, H))
    if x1 <= x0 or y1 <= y0:
        return img
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    rx, ry = xx - tx, yy - ty
    u = (rx * ux + ry * uy) / length
    v = -rx * uy + ry * ux
    uc = np.clip(u, 0, 1)
    prof = np.exp(-(v / (width * (0.15 + 0.85 * uc))) ** 2) * uc ** 1.6 * ((u >= 0) & (u <= 1.02))
    return _mix(img, x0, y0, (prof * alpha).astype(np.float32), color)


def _fade(tt, d, tin=0.12, tout=0.3):
    return clamp01(min(tt / tin, (d - tt) / tout))


# ---------------------------------------------------------------- the caption layouts
def cap_ignite(img, tt, d, text, tag, beat):
    """Vertical column at the right edge; characters rise in one by one beside a thin rule."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    n = len(text)
    step = min(150 * k, 0.62 * H / max(n, 1))
    S = int(step * 0.83)
    cx, y0 = 0.87 * W, 0.22 * H
    f = _fade(tt, d)
    lx = cx - S * 0.78
    top, bot = y0 - S * 0.55, y0 + (n - 1) * step + S * 0.55
    img = rule(img, (lx, top), (lx, top + (bot - top) * ease_out(tt / 0.9)), max(2, 3 * k), ACCENT, 0.9 * f)
    for i, ch in enumerate(text):
        ti = tt - 0.10 - i * 0.12
        if ti <= 0:
            continue
        rgb, a = char_sprite(ch, "serif_bold", S)
        img = blit(img, rgb, a, cx, y0 + i * step + 34 * k * (1 - ease_out(ti / 0.5)), 0, 1.0,
                   clamp01(ti / 0.2) * f)
    return img


def cap_bloom(img, tt, d, text, tag, beat):
    """Two left-aligned lines at the lower left, wiped in under an accent rule, optional small tag below."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    h = (len(text) + 1) // 2
    lines = [text[:h], text[h:]] if len(text) > 1 else [text]
    m = max(len(ln) for ln in lines)
    S = int(min(164 * k, 0.6 * W / (m + 0.14 * (m - 1))))
    x0, cy = 0.085 * W, 0.70 * H
    f = clamp01((d - tt) / 0.25)
    gy = S * 1.12
    img = rule(img, (x0, cy - S * 0.95), (x0 + 0.2 * W * ease_out(tt / 0.4), cy - S * 0.95),
               max(2, 3 * k), ACCENT, 0.9 * f)
    pad = int(S * 0.6)
    for i, line in enumerate(lines):
        ti = tt - 0.12 - i * 0.14
        if ti <= 0:
            continue
        rgb, a = wipe(run_sprite(line, "serif_black", S, 0.14), ease_out(ti / 0.5))
        img = blit(img, rgb, a, x0 - pad + a.shape[1] / 2, cy + i * gy, 0, 1.0, f)
    ts = tt - 0.7
    if tag and ts > 0:
        tsz = int(34 * k)
        rgb, a = run_sprite(tag, "sans_light", tsz, 0.45)
        img = blit(img, rgb, a, x0 - int(tsz * 0.6) + a.shape[1] / 2, cy + len(lines) * gy - S * 0.1, 0, 1.0,
                   clamp01(ts / 0.3) * f)
    return img


def cap_focus(img, tt, d, text, tag, beat):
    """Top centre; the letter-spacing contracts into focus as the line fades in, with a short rule under it."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    n = len(text)
    S = int(min(104 * k, 0.8 * W / (n + 1.2 * max(n - 1, 0))))
    f = _fade(tt, d)
    track = round(0.30 + 0.9 * (1 - ease_out(tt / 1.0)), 2)
    rgb, a = run_sprite(text, "serif_bold", S, track)
    img = blit(img, rgb, a, W / 2, 0.16 * H, 0, 1.0, clamp01(tt / 0.25) * f)
    half = 0.07 * W * ease_out((tt - 0.3) / 0.6)
    y = 0.16 * H + S * 0.78
    return rule(img, (W / 2 - half, y), (W / 2 + half, y), max(2, 3 * k), ACCENT, 0.9 * f)


def cap_meteors(img, tt, d, text, tag, beat):
    """Characters step down a gentle diagonal, each arriving on a thin white streak."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    n = len(text)
    S = int(128 * k)
    ang = 29.0
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    f = _fade(tt, d)
    sx = min(0.19 * W, 0.62 * W / max(n - 1, 1))
    sy = 0.18 * H / max(n - 1, 1)
    for i, ch in enumerate(text):
        ti = tt - i * 0.2
        if ti <= 0:
            continue
        e = ease_out(ti / 0.4)
        bx, by = 0.20 * W + i * sx, 0.17 * H + i * sy
        hx, hy = bx - ux * 520 * k * (1 - e), by - uy * 520 * k * (1 - e)
        al = clamp01(ti / 0.1) * f
        img = streak(img, hx, hy, ang, 420 * k * (1 - e), max(2, 3 * k), WHITE, 0.7 * (1 - e) * al)
        rgb, a = char_sprite(ch, "serif_bold", S)
        img = blit(img, rgb, a, hx, hy, 0, 1.0, al)
    return img


def cap_grand(img, tt, d, text, tag, beat):
    """Large line at the bottom, one character stamped in per beat, accent underline, optional tag."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    n = len(text)
    step = min(192 * k, 0.8 * W / max(n, 1))
    S = int(step * 0.78)
    cx, cy = W / 2, 0.80 * H
    f = _fade(tt, d, 0.1, 0.4)
    for i, ch in enumerate(text):
        ti = tt - i * beat
        if ti <= 0:
            continue
        rgb, a = char_sprite(ch, "serif_black", S)
        img = blit(img, rgb, a, cx + (i - (n - 1) / 2) * step, cy, 0, 1.2 - 0.2 * ease_out(ti / 0.3),
                   clamp01(ti / 0.08) * f)
    tl = tt - (n - 1) * beat - 0.2
    if tl > 0:
        half, y = (n - 1) / 2 * step + S * 0.5, cy + S * 0.72
        img = rule(img, (cx - half, y), (cx - half + 2 * half * ease_out(tl / 0.7), y), max(2, 3 * k), ACCENT, 0.9 * f)
        if tag:
            rgb, a = run_sprite(tag, "sans_light", int(32 * k), 0.5)
            img = blit(img, rgb, a, cx, y + 52 * k, 0, 1.0, clamp01((tl - 0.3) / 0.4) * f)
    return img


def cap_subtitle(img, tt, d, text, tag, beat):
    """Plain bottom subtitle for voiceover lines (wrapped to at most three lines)."""
    H, W = img.shape[:2]
    k = scale_k(W, H)
    S = int(54 * k)
    per = max(4, int(0.84 * W / (S * 1.04)))
    lines = (textwrap.wrap(text, per) if " " in text else [text[i:i + per] for i in range(0, len(text), per)])[:3]
    f = _fade(tt, d, 0.15, 0.2)
    y0 = 0.88 * H - (len(lines) - 1) * S * 0.7
    for i, line in enumerate(lines):
        rgb, a = run_sprite(line, "serif_bold", S, 0.04)
        img = blit(img, rgb, a, W / 2, y0 + i * S * 1.4, 0, 1.0, f)
    return img


LAYOUTS = {
    "ignite": (cap_ignite, "vertical column, right edge"),
    "bloom": (cap_bloom, "two left-aligned lines, lower left, with tag"),
    "focus": (cap_focus, "top centre, tracking contracts into focus"),
    "meteors": (cap_meteors, "diagonal cascade with meteor streaks"),
    "grand": (cap_grand, "bottom line stamped one character per beat"),
    "subtitle": (cap_subtitle, "plain bottom subtitle for voiceover"),
}


class Caption:
    def __init__(self, layout, text, t0, dur, tag="", beat=0.4):
        if layout not in LAYOUTS:
            raise ValueError(f"unknown caption layout '{layout}', choose from {sorted(LAYOUTS)}")
        self.layout, self.text, self.t0, self.dur, self.tag, self.beat = layout, text, t0, dur, tag, beat

    def draw(self, img, tg):
        tt = tg - self.t0
        if 0 <= tt < self.dur:
            return LAYOUTS[self.layout][0](img, tt, self.dur, self.text, self.tag, self.beat)
        return img


class TitleCard:
    """Big centred title with a small line under it; enters at 1.15x and settles in 0.5 s."""

    def __init__(self, text, subtitle, W, t0=0.10, dur=3.0):
        self.big = fit_run(text, "serif_black", 0.68 * W, 0.30)
        self.sub = fit_run(subtitle, "sans_light", 0.50 * W, 0.45) if subtitle else None
        self.t0, self.dur = t0, dur

    def draw(self, img, tg):
        tt = tg - self.t0
        if not 0 <= tt < self.dur:
            return img
        H, W = img.shape[:2]
        al = max(min(1.0, tt / 0.2, (self.dur - tt) / 0.2), 0.0)
        sc = 1 + 0.15 * max(0.0, 1 - tt / 0.5) ** 2
        img = blit(img, *self.big, W / 2, 0.55 * H, 0, sc, al)
        if self.sub:
            img = blit(img, *self.sub, W / 2, 0.61 * H, 0, sc, al)
        return img
