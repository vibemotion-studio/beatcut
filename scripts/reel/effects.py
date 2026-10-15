"""Per-frame image effects (剪映-style 特效) and the grade used by every reel.

Every catalog effect shares one signature: ``fn(img_u8_rgb, amt, t) -> img_u8_rgb`` where ``amt`` in
(0, 1] is the strength and ``t`` is seconds (drives deterministic animation). amt ~ 0 returns the input.
"""
import math

import cv2
import numpy as np

LUMA = np.array([.299, .587, .114], np.float32)


def _u8(x):
    return np.clip(x, 0, 255).astype(np.uint8)


def _warp(img, M):
    h, w = img.shape[:2]
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def scale_about_center(img, s, angle=0.0):
    h, w = img.shape[:2]
    return _warp(img, cv2.getRotationMatrix2D((w / 2, h / 2), angle, s))


# ---------------------------------------------------------------- building blocks
def sat(img, k):
    f = img.astype(np.float32)
    g = (f @ LUMA)[..., None]
    return _u8(g + (f - g) * k)


def rgb_split(img, px):
    a = int(round(px))
    if a < 1:
        return img
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], a, axis=1)
    out[..., 2] = np.roll(img[..., 2], -a, axis=1)
    return out


def bright(img, a):
    return _u8(img.astype(np.float32) * (1 + a) + 255 * a * 0.25)


def whip_frame(img, k):
    """Whip-spin burst around a cut: k in [-5, 4], the cut sits between k=-1 and k=0."""
    H, W = img.shape[:2]
    A = 34.0
    if k < 0:
        u = (k + 6) / 5.0
        ang = A * u ** 2.2
        prev = A * max(u - 0.2, 0) ** 2.2
    else:
        u = k / 5.0
        ang = -A * (1 - u) ** 2.2
        prev = -A * (1 - max(u - 0.2, 0)) ** 2.2 if k > 0 else ang + 8
    n = int(max(abs(ang - prev), 6.0) / 1.5) + 2
    acc = np.zeros(img.shape, np.float32)
    for a in np.linspace(prev, ang, n):
        acc += scale_about_center(img, 1.0 + 0.05 * abs(a) / A, float(a))
    return (acc / n).astype(np.uint8)


def radial_glow(W, H):
    """Center light-burst map in [0, 1], shape (H, W, 1)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    return (np.clip(1 - d / 1.15, 0, 1) ** 2.2)[..., None]


LOOKS = {   # vignette strength, contrast, saturation, warm bias
    "neutral": dict(vig=0.22, contrast=1.04, sat=1.04, warm=False),
    "night": dict(vig=0.38, contrast=1.08, sat=1.10, warm=True),
}


class Grade:
    """Vignette + contrast + saturation. 'night' adds a warm bias for fire and night scenes; 'neutral' stays honest."""

    def __init__(self, W, H, look="night"):
        if look not in LOOKS:
            raise ValueError(f"look must be one of {sorted(LOOKS)}, got {look!r}")
        self.p = LOOKS[look]
        yy, xx = np.mgrid[0:H, 0:W]
        d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        self.vig = (1 - self.p["vig"] * np.clip(d / 1.35, 0, 1) ** 1.8).astype(np.float32)[..., None]

    def __call__(self, img):
        f = img.astype(np.float32) * self.vig
        f = (f - 128) * self.p["contrast"] + 128
        g = (f @ LUMA)[..., None]
        f = g + (f - g) * self.p["sat"]
        if self.p["warm"]:
            f[..., 0] *= 1.03
            f[..., 2] *= 0.97
        return _u8(f)


# ---------------------------------------------------------------- catalog effects
def e_rgb_split(img, amt, t):
    return rgb_split(img, amt * 0.016 * img.shape[1])


def e_shake(img, amt, t):
    H, W = img.shape[:2]
    a = amt * 0.02 * W
    M = cv2.getRotationMatrix2D((W / 2, H / 2), amt * 1.2 * math.sin(t * 61.0), 1.0 + amt * 0.03)
    M[0, 2] += a * math.sin(t * 91.7) * math.cos(t * 43.1)
    M[1, 2] += a * math.sin(t * 77.3 + 1.1)
    return _warp(img, M)


def e_flash(img, amt, t):
    a = min(amt, 1.0)
    return _u8(img.astype(np.float32) * (1 - a) + 255 * a)


def e_glitch(img, amt, t):
    H, W = img.shape[:2]
    rng = np.random.default_rng(int(t * 30))
    out = img.copy()
    for _ in range(int(2 + amt * 8)):
        h = int(rng.integers(max(2, H // 80), max(3, H // 9)))
        y = int(rng.integers(0, max(1, H - h)))
        dx = int((rng.random() - 0.5) * amt * W * 0.25)
        out[y:y + h] = np.roll(out[y:y + h], dx, axis=1)
    return rgb_split(out, amt * 0.012 * W)


def e_zoom_pulse(img, amt, t):
    return scale_about_center(img, 1 + 0.12 * amt)


def e_mirror(img, amt, t):
    if amt < 0.5:
        return img
    W = img.shape[1]
    half = W // 2
    out = img.copy()
    out[:, W - half:] = img[:, :half][:, ::-1]
    return out


def e_mosaic(img, amt, t):
    if amt < 0.02:
        return img
    H, W = img.shape[:2]
    b = max(2, int(amt * 0.07 * W))
    small = cv2.resize(img, (max(1, W // b), max(1, H // b)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_NEAREST)


def e_grain(img, amt, t):
    rng = np.random.default_rng(int(t * 24))
    n = rng.normal(0, amt * 24, img.shape[:2]).astype(np.float32)[..., None]
    return _u8(img.astype(np.float32) + n)


def e_vhs(img, amt, t):
    H, W = img.shape[:2]
    f = rgb_split(img, amt * 0.008 * W).astype(np.float32)
    f[::3] *= 1 - 0.28 * amt
    y, h = int((t * 0.9 % 1.0) * H), max(2, int(H * 0.03))
    f[y:y + h] = np.roll(f[y:y + h], int(amt * W * 0.02 * math.sin(t * 40)), axis=1)
    g = (f @ LUMA)[..., None]
    return _u8(g + (f - g) * (1 - 0.25 * amt))


def e_letterbox(img, amt, t):
    h = int(img.shape[0] * 0.115 * min(amt, 1.0))
    if h < 1:
        return img
    out = img.copy()
    out[:h] = 0
    out[-h:] = 0
    return out


def e_radial_blur(img, amt, t):
    acc = np.zeros(img.shape, np.float32)
    n = 8
    for s in np.linspace(1.0, 1.0 + 0.14 * amt, n):
        acc += scale_about_center(img, float(s))
    return _u8(acc / n)


def e_motion_blur(img, amt, t):
    k = int(amt * 0.05 * img.shape[1]) | 1
    return img if k < 3 else cv2.blur(img, (k, 1))


def e_strobe(img, amt, t):
    on = int(t * 30) % 2 == 0
    return _u8(img.astype(np.float32) * ((1 + 0.55 * amt) if on else (1 - 0.40 * amt)))


def e_invert(img, amt, t):
    a = min(amt, 1.0)
    f = img.astype(np.float32)
    return _u8(f * (1 - a) + (255 - f) * a)


def e_blur(img, amt, t):
    sigma = amt * 0.012 * img.shape[1]
    return img if sigma < 0.5 else cv2.GaussianBlur(img, (0, 0), sigma)


_ripple_maps = {}


def e_ripple(img, amt, t):
    H, W = img.shape[:2]
    if (W, H) not in _ripple_maps:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        _ripple_maps[(W, H)] = (xx, yy)
    xx, yy = _ripple_maps[(W, H)]
    mx = xx + amt * 0.012 * W * np.sin(2 * np.pi * yy / (0.18 * H) + t * 8)
    return cv2.remap(img, mx, yy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def e_mono(img, amt, t):
    return sat(img, 1 - min(amt, 1.0))


# name -> (fn, 剪映 name, one-line description)
EFFECTS = {
    "rgb_split": (e_rgb_split, "色差", "red/blue channels pulled apart horizontally"),
    "shake": (e_shake, "抖动", "handheld shake with a slight roll"),
    "flash": (e_flash, "闪白", "blend toward white"),
    "glitch": (e_glitch, "故障", "horizontal slice tearing plus channel split"),
    "zoom_pulse": (e_zoom_pulse, "心跳/放大", "center punch-in, best on the beat"),
    "mirror": (e_mirror, "镜像", "left half mirrored onto the right (amt >= 0.5)"),
    "mosaic": (e_mosaic, "马赛克", "pixelate"),
    "grain": (e_grain, "胶片颗粒", "animated film grain"),
    "vhs": (e_vhs, "复古VHS", "scanlines, tracking jitter, soft color"),
    "letterbox": (e_letterbox, "电影黑边", "top and bottom bars"),
    "radial_blur": (e_radial_blur, "变焦模糊", "zoom blur streaking from the center"),
    "motion_blur": (e_motion_blur, "动感模糊", "horizontal motion blur"),
    "strobe": (e_strobe, "频闪", "alternate bright and dim frames"),
    "invert": (e_invert, "反色", "color inversion"),
    "blur": (e_blur, "模糊", "gaussian blur"),
    "ripple": (e_ripple, "水波纹", "sinusoidal ripple distortion"),
    "mono": (e_mono, "黑白", "drain color"),
}


def punch_env(lt, t0, tin=0.18, th=0.25, tout=0.7):
    """0 -> 1 -> hold -> 0 envelope starting at t0 (seconds into the shot)."""
    x = lt - t0
    if x < 0:
        return 0.0
    if x < tin:
        return x / tin * x / tin * (3 - 2 * x / tin)
    if x < tin + th:
        return 1.0
    if x < tin + th + tout:
        y = (x - tin - th) / tout
        return 1 - y * y * (3 - 2 * y)
    return 0.0


def effect_env(mode, tg, lt, dur, beat):
    """Strength envelope in [0, 1]. tg = global seconds, lt = seconds into the shot, dur = shot seconds."""
    if mode == "always":
        return 1.0
    if mode == "beat":
        return math.exp(-(tg % beat) / 0.07)
    if mode == "start":
        return math.exp(-lt / 0.25)
    if mode == "end":
        return math.exp(-max(dur - lt, 0.0) / 0.25)
    if mode == "ramp":
        return min(max(lt / max(dur, 1e-6), 0.0), 1.0)
    raise ValueError(f"unknown effect mode '{mode}'")
