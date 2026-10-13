"""Synthesized BGM: D major pentatonic, any bpm, any beat count (multiple of 4 recommended).

A drone and a pad run from the first to the last sample, so the track is never silent. Beat 0 is
at t=0 and every cut of the reel lands on this grid. The arrangement follows timing.sections(nb).
"""
import numpy as np

from . import synth as S
from .timing import DEFAULT_BPM, sections

PENT = (0, 2, 4, 7, 9)
SCALE = [50 + 12 * o + d for o in range(4) for d in PENT if 50 + 12 * o + d <= 93]
CHORDS = {"D": [50, 57, 62, 64], "B": [47, 54, 59, 62], "A": [45, 52, 57, 64], "E": [40, 47, 52, 57]}
ROOTS = {"D": 38, "B": 35, "A": 33, "E": 40}
FINAL = [50, 57, 62, 66, 69]
MOTIF = [[74, 76, 78, 81, 78, 76, 74, 69],
         [71, 74, 78, 81, 83, 81, 78, 76],
         [69, 74, 76, 81, 76, 74, 69, 66],
         [64, 69, 71, 76, 78, 76, 71, 69]]
TAIL = ["D", "E", "D", "B", "A", "D", "E", "D"]
PAD_LEVEL = {"intro": 0.5, "s2": 0.6, "groove": 0.7, "brk": 0.55, "bridge": 0.6,
             "chill": 0.65, "peak": 0.75, "ramp": 0.7, "fin": 0.9}


def bar_chords(nbars):
    out = ["DBAE"[i % 4] for i in range(nbars)]
    k = min(8, nbars)
    out[nbars - k:] = TAIL[8 - k:]
    return out


def render(nb, bpm=DEFAULT_BPM, seed=11):
    """Stereo float32 array (samples, 2), nb beats long, peak ~0.89."""
    S.reseed(seed)
    rng = S.rng()
    beat = 60.0 / bpm
    total_t = nb * beat
    N = int((total_t + 1.0) * S.SR)
    secs = sections(nb)
    sec = {sid: (st, b0, b1) for sid, st, b0, b1 in secs}

    def style(b):
        for _, st, b0, b1 in secs:
            if b0 <= b < b1:
                return st
        return "fin"

    nbars = (nb + 3) // 4
    chords = bar_chords(nbars)
    fin_bar0 = sec["fin"][1] // 4
    brk0, brk1 = sec["brk"][1:]
    brg0 = sec["bridge"][1]
    chl1 = sec["chill"][2]
    pk0, pk1 = sec["peak"][1:]
    rmp0 = sec["ramp"][1]
    fin0 = sec["fin"][1]
    accents = {max(1, brk0 - 4): 0.9, brk1: 0.9, pk0: 1.0, max(pk0 + 1, pk1 - 4): 0.8, fin0: 1.2, nb - 4: 1.3}
    accents = {b: g for b, g in accents.items() if 0 < b < nb}

    drums, basb, padb, lead, fx = (S.Bus(N) for _ in range(5))
    k_, tk_, cl_, hc_, ho_, cr_ = S.kick(), S.taiko(), S.clap(), S.hat(), S.hat(True), S.crash()
    pcache, plcache = {}, {}

    def lead_note(m, t, vel, pan=0.0, dur=1.5):
        key = (m, dur)
        if key not in plcache:
            plcache[key] = S.pluck(m, dur)
        lead.add(plcache[key], t, vel, pan)

    for b in range(nb):
        t0 = b * beat
        bar, bib = divmod(b, 4)
        st = style(b)
        ch = chords[bar]
        r = ROOTS[ch]
        last_bar = bar == nbars - 1

        if bib == 0:
            notes = FINAL if last_bar else CHORDS[ch]
            dur = 4 * beat + (1.6 if last_bar else 0.2)
            key = (tuple(notes), round(dur, 3))
            if key not in pcache:
                pcache[key] = S.pad(notes, dur)
            padb.addst(*pcache[key], t0, PAD_LEVEL[st])

        if b == 0:
            drums.add(tk_, 0.0, 1.0)
            drums.add(cr_, 0.0, 0.4)
        if b in accents:
            drums.add(tk_, t0, accents[b] * 0.9)
            drums.add(cr_, t0, 0.5 * accents[b])
            drums.add(k_, t0, 0.9)

        if st == "intro":
            if b in (4, 6):
                drums.add(k_, t0, 0.5)
        elif st == "s2":
            s0 = sec["s2"][1]
            if b >= s0 + 4 and bib % 2 == 0:
                drums.add(k_, t0, 0.55)
            if b >= s0 + 8:
                drums.add(hc_, t0 + beat / 2, 0.22)
        elif st in ("groove", "peak"):
            drums.add(k_, t0, 1.0 if st == "peak" else 0.9)
            if bib in (1, 3):
                drums.add(cl_, t0, 0.6)
            drums.add(hc_, t0, 0.18)
            drums.add(ho_, t0 + beat / 2, 0.26)
            if st == "peak":
                drums.add(hc_, t0 + beat / 4, 0.14)
                drums.add(hc_, t0 + 3 * beat / 4, 0.14)
        elif st == "bridge":
            for k in range(4):
                drums.add(cl_, t0 + k * beat / 4, 0.25 + 0.12 * k + 0.2 * (b - brg0))
        elif st == "chill":
            if bib in (0, 2):
                drums.add(k_, t0, 0.6 if bib == 0 else 0.4)
            if b >= chl1 - 2:
                for k in range(4):
                    drums.add(tk_, t0 + k * beat / 4, 0.25 + 0.15 * k + 0.2 * (b - (chl1 - 2)))
        elif st == "ramp":
            drums.add(k_, t0, 0.85)
            subs = (2, 2, 4, 8)[bib]
            for k in range(subs):
                drums.add(cl_, t0 + k * beat / subs, 0.3 + 0.1 * bib + 0.04 * k)
        elif st == "fin":
            if bib == 0 and b not in accents and bar <= nbars - 3:
                drums.add(tk_, t0, 0.7)
            if bar <= nbars - 4 and bib == 2:
                drums.add(k_, t0, 0.8)
            if bar == nbars - 2 and bib in (0, 2):
                drums.add(k_, t0, 0.6 if bib == 0 else 0.4)
            if bar <= nbars - 3:
                drums.add(ho_, t0 + beat / 2, 0.12)

        if st in ("groove", "peak", "ramp"):
            basb.add(S.bass(r, beat * 0.45), t0, 0.85)
            basb.add(S.bass(r + 12 if bib % 2 else r, beat * 0.4), t0 + beat / 2, 0.6)
        elif bib == 0:
            basb.add(S.bass(r, 4 * beat * 0.95), t0, 0.55 if st in ("intro", "s2") else 0.7)

        mo = MOTIF[bar % 4]
        pan = -0.4 if b % 2 else 0.4
        if st == "intro":
            if b >= 2 and bib in (0, 2):
                lead_note(mo[bib * 2], t0, 0.45)
        elif st in ("s2", "groove"):
            for k in range(2):
                lead_note(mo[bib * 2 + k], t0 + k * beat / 2, 0.5 if st == "s2" else 0.6, pan)
        elif st == "brk":
            lead_note(mo[bib * 2], t0, 0.4)
        elif st == "chill":
            lead_note(mo[bib * 2], t0, 0.5)
            lead_note(mo[bib * 2], t0 + beat * 0.75, 0.22, -pan)
        elif st in ("peak", "ramp"):
            for k in range(4):
                note = mo[bib * 2 + k // 2] + (12 if k % 2 else 0)
                lead_note(note, t0 + k * beat / 4, 0.5 if st == "peak" else 0.45, pan if k % 2 else -pan)
        elif st == "fin":
            fb = bar - fin_bar0
            if fb <= 4:
                dens = 4 if fb <= 2 else (2 if fb == 3 else 1)
                top = len(SCALE) - 1 - int(rng.integers(0, 4))
                for k in range(dens):
                    lead_note(SCALE[top - k * (1 if dens > 1 else 2)], t0 + k * beat / dens,
                              0.42 - 0.04 * fb, float(rng.uniform(-0.7, 0.7)), 1.8)
            if last_bar and bib == 0:
                for j, m in enumerate([62, 69, 74, 78, 81, 86]):
                    lead_note(m, t0 + j * 0.07, 0.6, (j - 2.5) * 0.25, 3.2)

    for t, d, g in ((brk0 * beat, 4 * beat, 0.5), (brg0 * beat, 2 * beat, 0.5),
                    (max(0, chl1 - 2) * beat, 2 * beat, 0.5), (rmp0 * beat, 4 * beat, 0.6)):
        fx.add(S.riser(d), t, g)

    t = np.arange(N) / S.SR
    breathe = 0.85 + 0.15 * np.sin(2 * np.pi * t / (8 * beat))
    drone = (0.5 * np.sin(2 * np.pi * 36.71 * t) + 0.35 * breathe * np.sin(2 * np.pi * 73.42 * t)
             + 0.12 * np.sin(2 * np.pi * 110.0 * t)) * np.minimum(1, t / 0.05) * 0.5

    amt = np.zeros(N)
    for _, st_, b0, b1 in secs:
        v = {"groove": 1.0, "peak": 1.0, "ramp": 1.0}.get(st_, 0.0)
        if st_ == "fin":
            v, b1 = 0.35, max(b0, nb - 4)
        if v:
            amt[int(b0 * beat * S.SR):int(b1 * beat * S.SR)] = v
    pump = 1 - amt * 0.5 * np.exp(-(t % beat) / 0.11)
    for bus in (padb, basb):
        bus.l *= pump
        bus.r *= pump

    pwl, pwr = S.verb(padb, N)
    lwl, lwr = S.verb(lead, N)
    dwl, dwr = S.verb(drums, N)
    left = (drums.l * 0.9 + basb.l * 0.8 + padb.l * 0.5 + lead.l * 0.8 + fx.l * 0.5 + drone * 0.45
            + pwl * 0.45 + lwl * 0.6 + dwl * 0.18)
    right = (drums.r * 0.9 + basb.r * 0.8 + padb.r * 0.5 + lead.r * 0.8 + fx.r * 0.5 + drone * 0.45
             + pwr * 0.45 + lwr * 0.6 + dwr * 0.18)
    out = np.stack([left, right], 1)[:int(total_t * S.SR)]
    out = np.tanh(out * 1.25) / np.tanh(1.25)
    out *= 0.89 / (np.abs(out).max() + 1e-9)
    fd = int(1.1 * S.SR)
    out[-fd:] *= np.linspace(1, 0, fd)[:, None]
    return out.astype(np.float32)
