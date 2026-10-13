"""Frame layouts: turn a landscape source frame into the output canvas (W x H)."""
import cv2
import numpy as np


def crop_v(src, cx, zoom, W, H):
    """Full-bleed crop of the source, centred horizontally on cx (0..1) and zoomed, scaled to W x H."""
    SH, SW = src.shape[:2]
    ch = SH / zoom
    cw = ch * W / H
    if cw > SW:
        cw = float(SW)
        ch = cw * H / W
    x0 = min(max(cx * SW - cw / 2, 0), SW - cw)
    y0 = (SH - ch) / 2
    s = W / cw
    M = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    return cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def blurfill(src, W, H):
    """Whole source frame centred on a dimmed, blurred copy of itself."""
    SH, SW = src.shape[:2]
    fh = int(round(W * SH / SW))
    bg = crop_v(src, 0.5, 1.0, W, H)
    if fh >= H:
        return bg
    bg = cv2.GaussianBlur(cv2.resize(bg, (max(1, W // 6), max(1, H // 6)), interpolation=cv2.INTER_AREA), (0, 0), 6)
    bg = (cv2.resize(bg, (W, H)) * 0.5).astype(np.uint8)
    y0 = (H - fh) // 2
    bg[y0:y0 + fh] = cv2.resize(src, (W, fh), interpolation=cv2.INTER_AREA)
    return bg


def triptych(clip, f, offsets, W, H):
    """Stack len(offsets) panels of the same clip, each delayed by an offset in frames (time-slice look)."""
    n = len(offsets)
    ph = min(int(round(W * clip.h / clip.w)), H // n - 4)
    gap = (H - n * ph) // (n + 1)
    out = np.zeros((H, W, 3), np.uint8)
    aspect = W / ph
    for k, off in enumerate(offsets):
        fr = clip.sample(f - off)
        sh, sw = fr.shape[:2]
        if sw / sh > aspect:
            cw = int(sh * aspect)
            x = (sw - cw) // 2
            fr = fr[:, x:x + cw]
        else:
            chh = int(sw / aspect)
            y = (sh - chh) // 2
            fr = fr[y:y + chh]
        top = gap + k * (ph + gap)
        out[top:top + ph] = cv2.resize(fr, (W, ph), interpolation=cv2.INTER_AREA)
    return out
