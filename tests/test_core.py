import numpy as np
import pytest

from reel import audio, bgm, effects, fonts, spec, text, timing, transitions
from reel.plan import build_plan
from reel.synth import SR


# ---------------------------------------------------------------- timing
@pytest.mark.parametrize("nb", [10, 12, 24, 40, 96, 200])
def test_sections_tile_exactly(nb):
    secs = timing.sections(nb)
    assert secs[0][2] == 0 and secs[-1][3] == nb
    for (_, _, _, b1), (_, _, b0, _) in zip(secs, secs[1:]):
        assert b1 == b0
    assert all(b1 - b0 >= 1 for _, _, b0, b1 in secs)


def test_sections_too_short():
    with pytest.raises(ValueError):
        timing.sections(timing.MIN_BEATS - 1)


def test_canonical_96_beats_matches_reference_grid():
    ends = [b1 for _, _, _, b1 in timing.sections(96)]
    assert ends == [8, 20, 32, 36, 44, 46, 52, 68, 72, 96]


# ---------------------------------------------------------------- spec
def test_normalize_defaults_and_isolation():
    a = spec.normalize({})
    a["captions"].append("x")
    assert spec.normalize({})["captions"] == []


@pytest.mark.parametrize("bad", [
    {"nope": 1},
    {"bpm": 10},
    {"beats": 3},
    {"transition": "swirl"},
    {"captions": [{"layout": "zzz", "text": "a", "at": "s2"}]},
    {"captions": [{"layout": "bloom", "text": "  ", "at": "s2"}]},
    {"captions": [{"layout": "bloom", "text": "a"}]},
    {"captions": [{"layout": "bloom", "text": "a", "at": "nowhere"}]},
    {"effects": [{"name": "zzz"}]},
    {"effects": [{"name": "glitch", "mode": "zzz"}]},
    {"effects": [{"name": "glitch", "from": 5, "to": 5}]},
    {"voiceover": [{"text": ""}]},
])
def test_normalize_rejects(bad):
    with pytest.raises(ValueError):
        spec.normalize(bad)


def test_parse_effect_and_caption():
    assert spec.parse_effect("glitch@52-68:beat:0.6") == {"name": "glitch", "from": 52.0, "to": 68.0, "mode": "beat", "amt": 0.6}
    assert spec.parse_effect("flash") == {"name": "flash"}
    assert spec.parse_caption("bloom:铁水成花@brk+0.2/1.5") == {
        "layout": "bloom", "text": "铁水成花", "at": "brk", "offset": 0.2, "dur": 1.5}
    for bad in ("", "glitch@5", "bloom:no-section"):
        with pytest.raises(ValueError):
            (spec.parse_effect if "@" in bad or bad == "" else spec.parse_caption)(bad)


# ---------------------------------------------------------------- effects / transitions
@pytest.fixture
def frame():
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (96, 54, 3), dtype=np.uint8)


@pytest.mark.parametrize("name", sorted(effects.EFFECTS))
def test_effect_contract(name, frame):
    fn = effects.EFFECTS[name][0]
    out = fn(frame, 0.8, 1.234)
    assert out.shape == frame.shape and out.dtype == np.uint8
    assert np.array_equal(fn(frame, 0.8, 1.234), out)          # deterministic
    assert np.abs(fn(frame, 0.0, 1.0).astype(int) - frame).mean() < 3   # amt 0 is (near) identity


@pytest.mark.parametrize("name", sorted(transitions.TRANSITIONS))
def test_transition_contract(name):
    a = np.full((96, 54, 3), 40, np.uint8)
    b = np.full((96, 54, 3), 200, np.uint8)
    fn = transitions.TRANSITIONS[name][0]
    mid = fn(a, b, 0.5)
    assert mid.shape == a.shape and mid.dtype == np.uint8
    assert np.abs(fn(a, b, 0.0).astype(int) - a).mean() < 12
    assert np.abs(fn(a, b, 1.0).astype(int) - b).mean() < 12


def test_effect_env_modes():
    assert effects.effect_env("always", 1, 0, 1, 0.4) == 1.0
    assert effects.effect_env("beat", 0.8, 0, 1, 0.4) == pytest.approx(1.0)
    assert effects.effect_env("ramp", 0, 0.5, 1.0, 0.4) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        effects.effect_env("zzz", 0, 0, 1, 0.4)


# ---------------------------------------------------------------- text
def test_caption_rejects_unknown_layout():
    with pytest.raises(ValueError):
        text.Caption("zzz", "a", 0, 1)


@pytest.mark.parametrize("layout", sorted(text.LAYOUTS))
def test_caption_layouts_draw_inside_canvas(layout):
    img = np.zeros((960, 540, 3), np.uint8)
    cap = text.Caption(layout, "铁水成花", 0.0, 4.0, tag="TAG", beat=0.4)
    assert cap.draw(img.copy(), -0.1).sum() == 0                 # before its window: untouched
    out = cap.draw(img.copy(), 2.5)
    assert out.shape == img.shape and out.sum() > 0              # it painted something
    assert cap.draw(img.copy(), 4.5).sum() == 0                  # after its window: untouched


def test_caption_text_is_flat_white():
    img = np.zeros((960, 540, 3), np.uint8)
    out = text.Caption("grand", "火树银花", 0.0, 6.0, beat=0.4).draw(img, 4.0)
    px = out.reshape(-1, 3)
    bright = px[px.max(1) > 240]
    assert len(bright) > 100
    assert (bright.min(1) > 235).mean() > 0.95                   # saturation ~0: no gold gradient


def test_font_override_missing_path():
    fonts.set_override("serif", "/no/such/font.ttf")
    try:
        with pytest.raises(FileNotFoundError):
            fonts.resolve("serif_bold")
    finally:
        fonts.set_override("serif", None)


# ---------------------------------------------------------------- plan
class FakeClip:
    def __init__(self, n):
        self.n = n

    def __len__(self):
        return self.n

    def windows(self, length=12, k=3):
        return [0, min(self.n - 1, 20)][:k]


@pytest.mark.parametrize("nb,nclips", [(12, 1), (24, 2), (40, 3), (96, 4)])
def test_plan_tiles_timeline(nb, nclips):
    clips = [FakeClip(100 + 20 * i) for i in range(nclips)]
    shots = build_plan(clips, nb, 152, 30, transition="whip")
    assert sum(s["n"] for s in shots) == timing.beat_frame(nb, 152, 30) or abs(
        sum(s["n"] for s in shots) - timing.beat_frame(nb, 152, 30)) <= len(shots)
    assert all(s["n"] >= 1 for s in shots)
    assert shots[-1]["kind"] == "finale" and shots[0]["kind"] == "hold"
    assert all(0 <= s["clip"] < nclips for s in shots if "clip" in s)


def test_plan_needs_clips():
    with pytest.raises(ValueError):
        build_plan([], 24, 152, 30)


# ---------------------------------------------------------------- audio
def test_bgm_never_silent_and_unclipped():
    a = bgm.render(12, 152)
    assert a.shape[1] == 2 and abs(len(a) / SR - 12 * 60 / 152) < 0.01
    assert np.abs(a).max() <= 0.9
    w = SR // 4
    rms = np.array([np.sqrt((a[i:i + w] ** 2).mean()) for i in range(0, len(a) - w, w)])
    assert rms.min() > 0.02


def test_bgm_deterministic():
    assert np.array_equal(bgm.render(12, 152, seed=3), bgm.render(12, 152, seed=3))


def test_duck_curve_dips_inside_span_only():
    g = audio.duck_curve(SR * 4, [(1.0, 2.0)], depth=0.5)
    assert g[int(0.2 * SR)] == pytest.approx(1.0, abs=0.01)
    assert g[int(1.5 * SR)] == pytest.approx(0.5, abs=0.02)
    assert g[int(3.5 * SR)] == pytest.approx(1.0, abs=0.01)


def test_mix_reel_peak_and_length():
    music = np.full((SR * 2, 2), 0.5, np.float32)
    out = audio.mix_reel(2.0, music, [], [0.5], None, [])
    assert out.shape == (SR * 2, 2) and np.abs(out).max() <= 0.9
