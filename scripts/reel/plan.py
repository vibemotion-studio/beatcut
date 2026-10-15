"""Shot planner: clips + a beat count -> the shot list the renderer plays.

The structure follows the reference reel: a bright-flash opening hold with the colorize reveal,
slow motion, a few quick plays, a hold, a continued play, a spin-through bridge, a second reveal,
a one-beat-per-cut montage, a time-slice triptych and a falling-spark finale.
Sections come from timing.sections(), so they scale with the beat count.
"""
from .timing import beat_frame, sections, smooth


def _chunks(b0, b1, size=4):
    """Split beats [b0, b1) into runs of ``size``; a trailing remainder under 2 beats joins the last run."""
    out, b = [], b0
    while b < b1:
        e = min(b + size, b1)
        if b1 - e < 2:
            e = b1
        out.append((b, e))
        b = e
    return out


def _fit_starts(shots, clips, warn):
    """Keep every shot's source range inside its clip. Shots that continue a previous one are only warned about."""
    for s in shots:
        if "clip" not in s:
            continue
        n_src = len(clips[s["clip"]])
        playing = s["kind"] in ("play", "tri", "finale")
        need = int(s["n"] * s.get("speed", 1.0)) + 1 if playing else 1
        if playing and s["name"] != "continue":
            s["f0"] = max(0, min(s["f0"], n_src - need))
        if s["f0"] + need > n_src and warn:
            warn(f"shot '{s['name']}' needs {need} frames of clip {s['clip'] + 1} from frame {s['f0']} but the clip "
                 f"has {n_src}; the last frame will hold")


def build_plan(clips, nb, bpm, fps, transition=None, trans_frames=6, warn=None):
    """Return a list of shot dicts tiling beats 0..nb exactly (sum of ``n`` == beat_frame(nb)).

    ``warn(message)`` is called for every shot whose source range does not fit its clip.
    """
    if not clips:
        raise ValueError("need at least one clip")
    E = lambda b: beat_frame(b, bpm, fps)
    nc = len(clips)
    wins = [c.windows(12, 4) or [0] for c in clips]
    win = lambda ci, r: wins[ci][r % len(wins[ci])]
    longest = max(range(nc), key=lambda i: len(clips[i]))
    cap = lambda ci, f: min(max(int(f), 0), len(clips[ci]) - 1)
    shots = []

    def add(sid, b0, b1, **kw):
        shots.append(dict(section=sid, b0=b0, b1=b1, n=max(1, E(b1) - E(b0)), **kw))

    def trans(extra=True):
        return (transition, trans_frames) if transition and extra else None

    cur = 1 % nc           # rotating clip index for the quick plays
    g_last = (0, 0)        # (clip, frame) where the last quick play ended, for the hold and the continuation
    for sid, _, b0, b1 in sections(nb):
        if sid == "intro":
            rv = min(2.4, 0.85 * (E(b1) - E(b0)) / fps)     # reveal must finish inside the shot
            add(sid, b0, b1, name="intro", kind="hold", clip=0, f0=win(0, 0), layout="track", zoom=1.0,
                push=0.05, q=lambda t, rv=rv: smooth(t / rv))
        elif sid == "s2":
            need = int((E(b1) - E(b0)) * 0.5) + 1      # source frames a half-speed play consumes
            add(sid, b0, b1, name="slow", kind="play", clip=0, f0=max(0, min(win(0, 0), len(clips[0]) - need)),
                speed=0.5, layout="track", zoom=1.12, trail=0.93, audio=0.35)
        elif sid == "groove1":
            ch = _chunks(b0, b1)
            for k, (cb0, cb1) in enumerate(ch):
                ci, last = cur % nc, k == len(ch) - 1
                cur += 1
                nfr = E(cb1) - E(cb0)
                add(sid, cb0, cb1, name=f"play{k + 1}", kind="play", clip=ci, f0=0 if last else win(ci, k),
                    speed=1.0, layout="track" if last else "blur", zoom=1.0,
                    trail=0.9 if (k % 2 == 1 and not last) else None,
                    punch=(min(1.1, 0.7 * nfr / fps), 1.4) if last else None, whip=last, pulse=True,
                    audio=0.4, trans=trans(k > 0))
                if last:
                    g_last = (ci, cap(ci, nfr))
        elif sid == "groove2":
            ci, f0 = g_last
            add(sid, b0, b1, name="continue", kind="play", clip=ci, f0=f0, speed=1.0, layout="track",
                zoom=lambda t: 1 + 0.4 * (1 - smooth(t / 0.8)), pulse=True, audio=0.4)
        elif sid == "brk":
            ci, f0 = g_last
            add(sid, b0, b1, name="hold", kind="hold", clip=ci, f0=f0, layout="track", zoom=1.4, push=0.04)
        elif sid == "bridge":
            d = max(0.05, (E(b1) - E(b0)) / fps - 0.02)
            add(sid, b0, b1, name="bridge", kind="bridge", q=lambda t, d=d: 1 - min(1.0, t / d), burst=True)
        elif sid == "chill":
            ci = cur % nc
            cur += 1
            rv = min(1.6, 0.85 * (E(b1) - E(b0)) / fps)
            add(sid, b0, b1, name="reveal2", kind="play", clip=ci, f0=0, speed=1.0, layout="track", zoom=1.0,
                q=lambda t, rv=rv: smooth(t / rv), audio=0.4, trans=trans())
        elif sid == "peak":
            for k in range(b1 - b0):
                ci = (k + 1) % nc
                add(sid, b0 + k, b0 + k + 1, name=f"cut{k + 1}", kind="play", clip=ci,
                    f0=win(ci, k // nc), speed=1.0, layout=("track", "blur", "track", "track")[k % 4],
                    zoom=1.35 if k % 4 == 2 else 1.0, whip=(k == 0), pulse=True)
        elif sid == "ramp":
            add(sid, b0, b1, name="triptych", kind="tri", clip=longest, f0=cap(longest, 34), offsets=[0, 5, 10],
                speed=1.0, whip=True, trans=trans())
        elif sid == "fin":
            fc = nc - 1
            add(sid, b0, b1, name="finale", kind="finale", clip=fc, f0=cap(fc, 30), speed=0.3, whip=True)
    _fit_starts(shots, clips, warn)
    return shots
