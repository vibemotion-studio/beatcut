"""Reel spec: defaults, validation and the small CLI string formats (--effect, --caption)."""
import re

from .effects import EFFECTS
from .text import LAYOUTS
from .timing import MIN_BEATS, SECTIONS
from .transitions import TRANSITIONS

SECTION_IDS = [s[0] for s in SECTIONS]
EFFECT_MODES = ("always", "beat", "start", "end", "ramp")
DEFAULTS = dict(title="", subtitle="", captions=[], voiceover=[], effects=[], transition=None, bpm=152, beats=96,
                bgm="synth", params={}, seed=11, voice="Ting-Ting", voice_subtitles=True, duck=0.5)


def _num(v, name, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {v!r}")
    if not lo <= x <= hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}], got {x}")
    return x


def _at(v, where):
    if isinstance(v, str) and v not in SECTION_IDS:
        raise ValueError(f"{where}: unknown section '{v}', choose from {SECTION_IDS}")
    return v


def normalize(spec):
    """Validate a spec dict and return a fresh, fully populated copy. Raises ValueError with a clear message."""
    spec = dict(spec or {})
    unknown = set(spec) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown spec keys {sorted(unknown)}; allowed: {sorted(DEFAULTS)}")
    s = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
         for k, v in {**DEFAULTS, **spec}.items()}
    s["bpm"] = _num(s["bpm"], "bpm", 60, 240)
    s["beats"] = int(_num(s["beats"], "beats", MIN_BEATS, 400))
    s["duck"] = _num(s["duck"], "duck", 0, 0.9)
    if s["transition"] is not None and s["transition"] not in TRANSITIONS:
        raise ValueError(f"unknown transition '{s['transition']}', choose from {sorted(TRANSITIONS)}")
    if not isinstance(s["bgm"], str) or not s["bgm"]:
        raise ValueError("bgm must be 'synth', 'none' or a path to an audio file")

    caps = []
    for i, c in enumerate(s["captions"]):
        w = f"captions[{i}]"
        if c.get("layout") not in LAYOUTS:
            raise ValueError(f"{w}: layout must be one of {sorted(LAYOUTS)}")
        if not str(c.get("text", "")).strip():
            raise ValueError(f"{w}: text is empty")
        if c.get("at") is None and c.get("beat") is None:
            raise ValueError(f"{w}: give 'at' (a section id) or 'beat'")
        caps.append(dict(layout=c["layout"], text=str(c["text"]), tag=str(c.get("tag", "")),
                         at=_at(c.get("at"), w), beat=c.get("beat"),
                         offset=_num(c.get("offset", 0.2), f"{w}.offset", -30, 300),
                         dur=_num(c.get("dur", 2.5), f"{w}.dur", 0.2, 60)))
    s["captions"] = caps

    vos = []
    for i, v in enumerate(s["voiceover"]):
        w = f"voiceover[{i}]"
        if not str(v.get("text", "")).strip():
            raise ValueError(f"{w}: text is empty")
        at = v.get("at")
        if at is not None and not isinstance(at, str):
            at = _num(at, f"{w}.at", 0, 3600)
        vos.append(dict(text=str(v["text"]), at=_at(at, w), offset=_num(v.get("offset", 0.0), f"{w}.offset", -30, 300)))
    s["voiceover"] = vos

    effs = []
    for i, e in enumerate(s["effects"]):
        w = f"effects[{i}]"
        if e.get("name") not in EFFECTS:
            raise ValueError(f"{w}: name must be one of {sorted(EFFECTS)}")
        mode = e.get("mode", "beat")
        if mode not in EFFECT_MODES:
            raise ValueError(f"{w}: mode must be one of {EFFECT_MODES}")
        lo, hi = _num(e.get("from", 0), f"{w}.from", 0, 400), _num(e.get("to", s["beats"]), f"{w}.to", 0, 400)
        if hi <= lo:
            raise ValueError(f"{w}: 'to' must be greater than 'from'")
        effs.append(dict(name=e["name"], mode=mode, amt=_num(e.get("amt", 0.6), f"{w}.amt", 0, 1.5), **{"from": lo, "to": hi}))
    s["effects"] = effs
    return s


def parse_effect(text):
    """'glitch@52-68:beat:0.6' -> effect dict (mode and amt optional; range optional)."""
    m = re.fullmatch(r"(\w+)(?:@(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?))?(?::(\w+))?(?::(\d*\.?\d+))?", text.strip())
    if not m:
        raise ValueError(f"bad --effect '{text}'; use name[@from-to][:mode][:amt], e.g. glitch@52-68:beat:0.6")
    name, lo, hi, mode, amt = m.groups()
    e = {"name": name}
    if lo is not None:
        e["from"], e["to"] = float(lo), float(hi)
    if mode:
        e["mode"] = mode
    if amt:
        e["amt"] = float(amt)
    return e


def parse_caption(text):
    """'bloom:铁水成花@brk+0.2/1.5' -> caption dict (offset and duration optional)."""
    m = re.fullmatch(r"(\w+):(.+?)@(\w+)(?:\+(-?\d+(?:\.\d+)?))?(?:/(\d+(?:\.\d+)?))?", text.strip())
    if not m:
        raise ValueError(f"bad --caption '{text}'; use layout:text@section[+offset][/dur], e.g. bloom:铁水成花@brk+0.2/1.5")
    layout, body, at, off, dur = m.groups()
    c = {"layout": layout, "text": body, "at": at}
    if off is not None:
        c["offset"] = float(off)
    if dur is not None:
        c["dur"] = float(dur)
    return c
