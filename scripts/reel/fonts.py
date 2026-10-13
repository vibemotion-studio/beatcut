"""CJK font lookup. Roles: serif_black, serif_bold, serif, sans_light.

Override with the REEL_FONT_SERIF / REEL_FONT_SANS environment variables (``path`` or ``path:index``),
or call set_override(). The macOS defaults are Songti SC (titles) and PingFang SC Light (small tags).
"""
import os
from pathlib import Path

from PIL import ImageFont

_MAC_SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
_MAC_PING = "/System/Library/Fonts/PingFang.ttc"
_NOTO = "/usr/share/fonts/opentype/noto/"
_WIN = "C:/Windows/Fonts/"

CANDIDATES = {
    "serif_black": [(_MAC_SONGTI, 0), (_NOTO + "NotoSerifCJK-Black.ttc", 2), (_WIN + "simsun.ttc", 0)],
    "serif_bold": [(_MAC_SONGTI, 1), (_NOTO + "NotoSerifCJK-Bold.ttc", 2), (_WIN + "simsun.ttc", 0)],
    "serif": [(_MAC_SONGTI, 6), (_NOTO + "NotoSerifCJK-Regular.ttc", 2), (_WIN + "simsun.ttc", 0)],
    "sans_light": [(_MAC_PING, 11), (_NOTO + "NotoSansCJK-Light.ttc", 2), (_WIN + "msyhl.ttc", 0)],
}
_override: dict = {"serif": None, "sans": None}
_cache = {}


def _parse(spec):
    path, _, idx = spec.partition(":")
    if idx.isdigit() and not Path(spec).exists():
        return path, int(idx)
    return spec, 0


def set_override(group, spec):
    """group: 'serif' or 'sans'; spec: 'path' or 'path:index' (None clears)."""
    _override[group] = _parse(spec) if spec else None
    _cache.clear()


def _group(role):
    return "sans" if role.startswith("sans") else "serif"


def resolve(role):
    group = _group(role)
    ov = _override[group] or (_parse(os.environ[f"REEL_FONT_{group.upper()}"])
                              if os.environ.get(f"REEL_FONT_{group.upper()}") else None)
    if ov:
        if not Path(ov[0]).exists():
            raise FileNotFoundError(f"font override not found: {ov[0]}")
        return ov
    for path, idx in CANDIDATES[role]:
        if Path(path).exists():
            return path, idx
    raise RuntimeError(f"no CJK font found for role '{role}'; set REEL_FONT_{group.upper()}=/path/to/font.ttc[:index]")


def get_font(role, size):
    size = max(6, int(round(size)))
    key = (role, size)
    if key not in _cache:
        path, idx = resolve(role)
        _cache[key] = ImageFont.truetype(path, size, index=idx)
    return _cache[key]
