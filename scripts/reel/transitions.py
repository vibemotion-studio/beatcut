"""Two-sided transitions: ``fn(a_u8, b_u8, p) -> img`` with p in [0, 1].

p=0 returns A, p=1 returns B. A is the outgoing shot's last frame (held), B the incoming shot's live frame.
"""
import math

import cv2
import numpy as np

from .effects import (_u8, _warp, e_flash, e_glitch, e_mosaic, e_motion_blur, e_radial_blur,
                      scale_about_center)
from .timing import smooth


def t_fade(a, b, p):
    return cv2.addWeighted(a, 1 - p, b, p, 0)


def t_slide(a, b, p):
    W = a.shape[1]
    s = int(round(W * smooth(p)))
    if s <= 0:
        return a.copy()
    if s >= W:
        return b.copy()
    out = np.empty_like(a)
    out[:, :W - s] = a[:, s:]
    out[:, W - s:] = b[:, :s]
    return out


def t_zoom(a, b, p):
    e = smooth(p)
    out = scale_about_center(a, 1 + 0.9 * e).astype(np.float32) * (1 - e) \
        + scale_about_center(b, 1.6 - 0.6 * e).astype(np.float32) * e
    return e_radial_blur(_u8(out), 0.8 * math.sin(math.pi * p), 0)


def t_whip(a, b, p):
    H, W = a.shape[:2]
    if p < 0.5:
        src, shift = a, -0.35 * W * smooth(p * 2)
    else:
        src, shift = b, 0.35 * W * (1 - smooth((p - 0.5) * 2))
    moved = _warp(src, np.array([[1, 0, shift], [0, 1, 0]], np.float32))
    return e_motion_blur(moved, 1.6 * math.sin(math.pi * p), 0)


def t_glitch(a, b, p):
    return e_glitch(a if p < 0.5 else b, math.sin(math.pi * p), p * 9)


def t_flash(a, b, p):
    return e_flash(a if p < 0.5 else b, math.sin(math.pi * p) ** 0.7, 0)


def t_wipe(a, b, p, soft=0.18):
    H, W = a.shape[:2]
    soft_px = max(2.0, soft * W)
    x = np.arange(W, dtype=np.float32)
    m = np.clip((p * (W + soft_px) - x) / soft_px, 0, 1)[None, :, None]
    return _u8(a.astype(np.float32) * (1 - m) + b.astype(np.float32) * m)


def t_spin(a, b, p):
    e = smooth(p)
    A = scale_about_center(a, 1 + 0.5 * e, 30 * e).astype(np.float32)
    B = scale_about_center(b, 1 + 0.5 * (1 - e), -30 * (1 - e)).astype(np.float32)
    return _u8(A * (1 - e) + B * e)


def t_mosaic(a, b, p):
    return e_mosaic(a if p < 0.5 else b, math.sin(math.pi * p), 0)


# name -> (fn, 剪映 name, one-line description)
TRANSITIONS = {
    "fade": (t_fade, "叠化", "cross-dissolve"),
    "slide": (t_slide, "推移", "push the old shot out to the left"),
    "zoom": (t_zoom, "拉近/放大", "zoom through with radial blur"),
    "whip": (t_whip, "快速横移", "whip pan with horizontal blur"),
    "glitch": (t_glitch, "故障", "tearing hard cut"),
    "flash": (t_flash, "闪白", "dip to white"),
    "wipe": (t_wipe, "擦除", "soft left-to-right wipe"),
    "spin": (t_spin, "旋转", "rotate and scale dissolve"),
    "mosaic": (t_mosaic, "马赛克", "pixelate through the cut"),
}
