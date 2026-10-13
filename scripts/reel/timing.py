"""Beat grid, easing and the section plan shared by the planner, the BGM and the renderer."""

FPS = 30
DEFAULT_BPM = 152
CANON_BEATS = 96

# (id, style, canonical end beat). The style drives the BGM arrangement and the visual plan.
SECTIONS = [
    ("intro", "intro", 8),
    ("s2", "s2", 20),
    ("groove1", "groove", 32),
    ("brk", "brk", 36),
    ("groove2", "groove", 44),
    ("bridge", "bridge", 46),
    ("chill", "chill", 52),
    ("peak", "peak", 68),
    ("ramp", "ramp", 72),
    ("fin", "fin", 96),
]
MIN_BEATS = len(SECTIONS)


def beat_seconds(bpm):
    return 60.0 / bpm


def beat_frame(b, bpm=DEFAULT_BPM, fps=FPS):
    return int(round(b * 60.0 / bpm * fps))


def sections(nb):
    """[(id, style, b0, b1)] covering beats 0..nb. Boundaries scale with nb, each section is >= 1 beat."""
    if nb < MIN_BEATS:
        raise ValueError(f"need at least {MIN_BEATS} beats, got {nb}")
    out, prev = [], 0
    last = len(SECTIONS) - 1
    for i, (sid, style, end) in enumerate(SECTIONS):
        b1 = nb if i == last else max(prev + 1, round(end * nb / CANON_BEATS))
        b1 = min(b1, nb - (last - i))
        out.append((sid, style, prev, b1))
        prev = b1
    return out


def clamp01(x):
    return min(max(x, 0.0), 1.0)


def smooth(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def back_out(x, s=1.9):
    x = clamp01(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
