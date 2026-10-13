"""Procedural 铁花 finale light layer.

Particle positions are closed-form (gravity + linear drag), so any frame renders on its own:
    sh = Shower(beat, beats, W, H);  lay = sh.layer(t)        # float32 HxWx3 additive light, t from finale start
    out = composite(base_u8_rgb, lay, dim=0.5)                # screen-blend over dimmed footage

Wave times are given in beats of a 24-beat canon and scaled down when the finale is shorter, so the
bursts land on the BGM grid. Falling speed is capped near 630 px/s (grav*tau at 1920 px tall).
"""
import cv2
import numpy as np

K = 8              # trail samples per particle
DT_TRAIL = 0.008   # seconds between trail samples

# colour over normalised age: white-hot -> gold -> orange -> ember red
_RAMP_T = np.array([0.0, 0.18, 0.5, 0.82, 1.0])
_RAMP = np.array([[1.0, 0.97, 0.85], [1.0, 0.78, 0.30], [1.0, 0.42, 0.08],
                  [0.75, 0.16, 0.03], [0.30, 0.05, 0.01]], np.float32)


def _color(u):
    return np.stack([np.interp(u, _RAMP_T, _RAMP[:, c]) for c in range(3)], 1).astype(np.float32)


class Shower:
    def __init__(self, beat, beats, W, H, seed=5):
        self.W, self.H = W, H
        g = np.random.default_rng(seed)
        s = H / 1920.0                                        # lengths and speeds scale with canvas height
        areaf = max(0.25, W * H / (1080 * 1920.0))            # particle counts scale with canvas area
        cnt = lambda n: max(40, int(n * areaf))
        sc = min(1.0, max(beats, 12) / 24.0)
        T = lambda b: b * sc * beat
        P = []
        self.bursts = []    # (t, cx, cy, bloom gain, bloom radius scale)
        self.flashes = []   # (t, amplitude) full-frame white flashes

        def add(n, birth, x0, y0, vx, vy, life, grav, tau, size, gain):
            f = lambda v: np.broadcast_to(np.asarray(v, np.float32), (n,)).copy()
            P.append(np.stack([f(birth), f(x0), f(y0), f(vx), f(vy), f(life), f(grav), f(tau), f(size), f(gain)], 1))

        def fountain(t0, t1, n):
            n = cnt(n)   # thrown from the bottom centre; apex about 1.2 s after birth
            ang = g.normal(0, 0.30, n)
            sp = np.clip(g.lognormal(np.log(2300 * s), 0.30, n), 1200 * s, 3600 * s)
            add(n, g.uniform(t0, t1, n), W * 0.5 + g.normal(0, 30 * s, n), H * 0.98,
                sp * np.sin(ang), -sp * np.cos(ang), g.uniform(2.2, 3.4, n), 1200 * s, 1.5,
                g.uniform(1, 2.2, n), 1.0)

        def burst(b, cx, cy, n, med, bloom=1.0, rad=1.0):
            n, t = cnt(n), T(b)
            a = g.uniform(0, 2 * np.pi, n)
            sp = np.clip(g.lognormal(np.log(med * s), 0.45, n), 100 * s, 1700 * s)
            add(n, t + g.uniform(0, 0.04, n), W * cx + g.normal(0, 5 * s, n), H * cy + g.normal(0, 5 * s, n),
                sp * np.cos(a), sp * np.sin(a) - 80 * s, g.uniform(2.2, 3.6, n), 700 * s, 1.0,
                g.uniform(1, 2.2, n), 1.35)
            self.bursts.append((t, cx, cy, bloom, rad))

        f1 = max(0.0, T(3) - 1.2)
        fountain(f1, f1 + 0.8, 3200)
        burst(3, 0.50, 0.32, 3200, 640, 1.0)
        burst(4, 0.28, 0.40, 1500, 480, 0.6)
        burst(5, 0.76, 0.36, 1500, 480, 0.6)
        burst(8, 0.30, 0.36, 2400, 540, 0.8)
        burst(10, 0.72, 0.28, 2400, 540, 0.8)
        burst(12, 0.50, 0.34, 4500, 700, 1.4, 1.3)
        for cx, cy in ((0.22, 0.50), (0.78, 0.45), (0.50, 0.22)):
            burst(16, cx, cy, 2500, 520, 0.8)
        f2 = max(0.0, T(20) - 1.6)    # second fountain peaks exactly on the grand bloom
        fountain(f2, f2 + 0.6, 2500)
        burst(20, 0.50, 0.36, 7000, 780, 2.2, 1.8)
        for cx, cy in ((0.20, 0.30), (0.80, 0.30), (0.25, 0.62), (0.75, 0.60)):
            burst(20.1, cx, cy, 2600, 560, 1.0)
        self.flashes = [(T(3), 0.20), (T(12), 0.25), (T(20), 0.50)]

        n = cnt(13000)   # falling curtain across the full width
        add(n, g.uniform(T(3), T(18.7), n), g.uniform(-0.05 * W, 1.05 * W, n), g.uniform(-80 * s, 0.08 * H, n),
            g.normal(0, 70 * s, n), g.uniform(120 * s, 420 * s, n), g.uniform(3.0, 4.4, n), 900 * s, 0.7,
            g.uniform(1, 2.2, n), 1.0)
        n = cnt(5000)    # heavier shower right after the grand bloom
        add(n, g.uniform(T(20), T(21.5), n), g.uniform(-0.05 * W, 1.05 * W, n), g.uniform(-80 * s, 0.08 * H, n),
            g.normal(0, 70 * s, n), g.uniform(120 * s, 420 * s, n), g.uniform(2.5, 3.5, n), 900 * s, 0.7,
            g.uniform(1, 2.2, n), 1.1)
        n = cnt(3500)    # splash where the curtain lands
        add(n, g.uniform(T(10.6), T(23.3), n), g.uniform(0.02 * W, 0.98 * W, n), H * 0.965,
            g.normal(0, 380 * s, n), -g.uniform(150 * s, 650 * s, n), g.uniform(0.5, 1.1, n), 1800 * s, 1.8,
            g.uniform(1, 1.8, n), 0.9)
        n = cnt(1200)    # slow embers
        add(n, g.uniform(T(3.8), T(20.2), n), g.uniform(0, W, n), g.uniform(0.1 * H, 0.9 * H, n),
            g.normal(0, 25 * s, n), g.uniform(-30 * s, 20 * s, n), g.uniform(1.6, 3.2, n), 90 * s, 0.8,
            g.uniform(1.5, 2.5, n), 0.6)

        a = np.concatenate(P, 0)
        (self.birth, self.x0, self.y0, self.vx, self.vy, self.life,
         self.grav, self.tau, self.size, self.gain) = (a[:, i] for i in range(10))
        self.phase = g.uniform(0, 6.28, len(a)).astype(np.float32)
        self.freq = g.uniform(14, 40, len(a)).astype(np.float32)
        self.end = float((self.birth + self.life).max())
        self.blur_s = max(1.0, s)

    def _pos(self, idx, age):
        tau = self.tau[idx]
        e = 1 - np.exp(-age / tau)
        x = self.x0[idx] + self.vx[idx] * tau * e
        y = self.y0[idx] + self.grav[idx] * tau * age + (self.vy[idx] - self.grav[idx] * tau) * tau * e
        return x, y

    def layer(self, t):
        W, H = self.W, self.H
        age = t - self.birth
        idx = np.nonzero((age >= 0) & (age <= self.life))[0]
        acc = np.zeros((3, H * W), np.float32)
        if len(idx):
            a0 = age[idx]
            u = a0 / self.life[idx]
            flick = 0.78 + 0.22 * np.sin(a0 * self.freq[idx] + self.phase[idx])
            base = (1 - u) ** 0.85 * flick * self.gain[idx]
            col = _color(u)
            big = self.size[idx] > 1.8
            fl, ws = [], []
            for j in range(K):
                x, y = self._pos(idx, np.maximum(a0 - j * DT_TRAIL, 0))
                xi = np.rint(x).astype(np.int32)
                yi = np.rint(y).astype(np.int32)
                ok = (xi >= 0) & (xi < W - 1) & (yi >= 0) & (yi < H - 1)
                if not ok.any():
                    continue
                w = (base * (1 - j / K))[ok][:, None] * col[ok]
                flat = yi[ok] * W + xi[ok]
                fl.append(flat)
                ws.append(w)
                b = big[ok]
                if b.any():
                    for off in (1, W, W + 1):
                        fl.append(flat[b] + off)
                        ws.append(w[b])
            if fl:
                flat = np.concatenate(fl)
                w = np.concatenate(ws)
                for c in range(3):
                    acc[c] = np.bincount(flat, weights=w[:, c], minlength=H * W)
        lay = np.ascontiguousarray(acc.reshape(3, H, W).transpose(1, 2, 0))
        small = cv2.resize(lay, (max(1, W // 4), max(1, H // 4)), interpolation=cv2.INTER_AREA)
        glow = cv2.resize(cv2.GaussianBlur(small, (0, 0), 9 * H / 1920.0 + 0.5), (W, H),
                          interpolation=cv2.INTER_LINEAR) * 1.6
        out = lay + cv2.GaussianBlur(lay, (0, 0), 3.5 * self.blur_s) * 0.9 + glow
        for tb, cx, cy, gain, rad in self.bursts:
            d = t - tb
            if 0 <= d < 0.5:
                yy, xx = np.mgrid[0:H:4, 0:W:4]
                r2 = ((xx - W * cx) ** 2 + (yy - H * cy) ** 2) / (W * 0.30 * rad) ** 2
                blob = (np.exp(-r2) * np.exp(-d / 0.12) * gain * 1.4).astype(np.float32)
                out = out + cv2.resize(blob, (W, H))[..., None] * np.array([1.0, 0.72, 0.32], np.float32)
        for tf, amp in self.flashes:
            d = t - tf
            if 0 <= d < 0.7:
                out = out + amp * np.exp(-d / 0.18) * np.array([1.0, 0.92, 0.80], np.float32)
        return out.astype(np.float32)


def composite(base_u8, lay, dim=0.6):
    """Screen-blend an additive light layer over footage dimmed by ``dim``."""
    b = base_u8.astype(np.float32) / 255 * dim
    l = 1 - np.exp(-np.clip(lay, 0, None) * 1.25)
    return np.clip((1 - (1 - b) * (1 - l)) * 255, 0, 255).astype(np.uint8)
