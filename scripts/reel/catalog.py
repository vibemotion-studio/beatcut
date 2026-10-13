"""Human-readable catalog of everything the skill can do (printed by make_reel.py --list)."""
from .effects import EFFECTS
from .text import LAYOUTS
from .timing import SECTIONS
from .transitions import TRANSITIONS


def describe():
    lines = ["Effects  (--effect name[@from-to][:mode][:amt]; modes: always beat start end ramp)"]
    lines += [f"  {k:12s} {zh:8s} {d}" for k, (_, zh, d) in EFFECTS.items()]
    lines += ["", "Transitions  (--transition NAME, applied at the cuts between quick plays, reveal and triptych)"]
    lines += [f"  {k:12s} {zh:8s} {d}" for k, (_, zh, d) in TRANSITIONS.items()]
    lines += ["", "Caption layouts  (--caption layout:text@section[+offset][/dur])"]
    lines += [f"  {k:12s} {d}" for k, (_, d) in LAYOUTS.items()]
    lines += ["", "Sections  (use as 'at'; boundaries scale with --beats)"]
    lines += [f"  {sid:8s} {st:7s} ends at canonical beat {end}" for sid, st, end in SECTIONS]
    return "\n".join(lines)
