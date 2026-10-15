import numpy as np
import pytest

from reel import audio, bgm, effects, fonts, media, spec, text, timing, transitions
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
    {"voiceover": [{"text": "", "file": ""}]},
    {"look": "sepia"},
    {"tts": "espeak"},
    {"typeface": "mono"},
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


@pytest.mark.parametrize("nb", [24, 40, 64, 96])
def test_reveals_finish_inside_their_shot(nb):
    shots = build_plan([FakeClip(150), FakeClip(120)], nb, 152, 30)
    reveals = [s for s in shots if s.get("name") in ("intro", "reveal2")]
    assert reveals
    for s in reveals:
        assert s["q"]((s["n"] - 1) / 30) == pytest.approx(1.0)


@pytest.mark.parametrize("beats", [12, 16, 24, 32])
def test_grand_bloom_precedes_closing_fade(beats):
    from reel.sparks import Shower
    beat = 60 / 152
    sh = Shower(beat, beats, 108, 192)
    assert sh.flashes[-1][0] + 1.3 <= beats * beat + 1e-6


def test_full_length_finale_timing_unchanged():
    from reel.sparks import Shower
    beat = 60 / 152
    assert Shower(beat, 24, 108, 192).flashes[-1][0] == pytest.approx(20 * beat)


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


def test_prepare_voice_trims_silence_and_sets_loudness():
    sig = np.zeros((SR * 2, 2), np.float32)
    sig[SR:SR + SR // 2] = 0.3 * np.sin(np.linspace(0, 400, SR // 2))[:, None]
    out = audio.prepare_voice(sig)
    assert len(out) < SR * 0.7
    assert np.sqrt((out ** 2).mean()) == pytest.approx(audio.VOICE_RMS, rel=0.25)
    assert np.abs(out).max() <= 0.9 + 1e-6
    with pytest.raises(ValueError):
        audio.prepare_voice(np.zeros((SR, 2), np.float32))


def test_resolve_engine(monkeypatch):
    with pytest.raises(ValueError):
        audio.resolve_engine("espeak")
    monkeypatch.setattr(audio, "edge_available", lambda: True)
    monkeypatch.setattr(audio, "say_available", lambda: True)
    assert audio.resolve_engine("auto") == "edge"
    monkeypatch.setattr(audio, "edge_available", lambda: False)
    assert audio.resolve_engine("auto") == "say"
    monkeypatch.setattr(audio, "say_available", lambda: False)
    with pytest.raises(RuntimeError, match="edge-tts"):
        audio.resolve_engine("auto")
    with pytest.raises(RuntimeError, match="not installed"):
        audio.resolve_engine("edge")


def test_synthesize_voice_routes_to_engine_and_caches(tmp_path, monkeypatch):
    from scipy.io import wavfile
    calls = []

    def fake_edge(text, voice, out):
        calls.append((text, voice))
        wavfile.write(str(out), 24000, (0.2 * np.sin(np.linspace(0, 900, 24000)) * 32767).astype(np.int16))

    monkeypatch.setattr(audio, "edge_available", lambda: True)
    monkeypatch.setattr(audio, "_edge", fake_edge)
    a = audio.synthesize_voice("你好", None, tmp_path, "edge")
    audio.synthesize_voice("你好", None, tmp_path, "edge")
    assert len(calls) == 1 and calls[0][1] == audio.DEFAULT_VOICE["edge"]     # the second call hits the cache
    assert a.shape[1] == 2 and abs(len(a) / SR - 1.0) < 0.05
    audio.synthesize_voice("你好", "zh-CN-XiaoxiaoNeural", tmp_path, "edge")
    assert len(calls) == 2                                                    # another voice is another cache entry
    with pytest.raises(ValueError):
        audio.synthesize_voice("  ", None, tmp_path, "edge")


def test_decode_rejects_files_without_audio(tmp_path):
    import subprocess
    silent = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", str(silent)], check=True)
    with pytest.raises(ValueError, match="no audio stream"):
        audio.decode(silent)
    with pytest.raises(FileNotFoundError):
        audio.decode(tmp_path / "missing.wav")


# ---------------------------------------------------------------- media / fonts / grade / params
def test_decode_size_keeps_aspect_and_never_upscales():
    assert media.decode_size(1920, 1080, 960) == (960, 540)
    assert media.decode_size(1080, 1920, 960) == (540, 960)
    assert media.decode_size(640, 360, 1920) == (640, 360)


def test_clean_cache_only_touches_decode_files(tmp_path):
    (tmp_path / "0123456789abcdef.u8").write_bytes(b"x" * 10)
    (tmp_path / "0123456789abcdef.part").write_bytes(b"x" * 5)
    keep = [tmp_path / "notes.txt", tmp_path / "vo_abc.mp3"]
    for p in keep:
        p.write_bytes(b"y")
    assert media.cache_bytes(tmp_path) == 15
    assert media.clean_cache(tmp_path) == 15
    assert media.cache_bytes(tmp_path) == 0
    assert all(p.exists() for p in keep)


def test_typeface_sans_maps_serif_roles():
    fonts.set_typeface("sans")
    try:
        assert fonts._effective("serif_black") == "sans_semibold"
        assert fonts._effective("sans_light") == "sans_light"
    finally:
        fonts.set_typeface("serif")
    assert fonts._effective("serif_black") == "serif_black"
    with pytest.raises(ValueError):
        fonts.set_typeface("mono")


def test_grade_looks_differ_and_unknown_is_rejected():
    img = np.full((48, 27, 3), 120, np.uint8)
    assert not np.array_equal(effects.Grade(27, 48, "neutral")(img), effects.Grade(27, 48, "night")(img))
    with pytest.raises(ValueError):
        effects.Grade(27, 48, "sepia")


def test_effect_params_night_tuning_only_for_night_look():
    from reel.render import effect_params
    assert effect_params(look="neutral")["bloom"] != effect_params(look="night")["bloom"]
    with pytest.raises(ValueError):
        effect_params({"nope": 1})


def test_voiceover_accepts_a_file_without_text():
    s = spec.normalize({"voiceover": [{"file": "a.wav", "at": "s2"}]})
    assert s["voiceover"][0]["file"] == "a.wav" and s["voiceover"][0]["text"] == ""


def test_plan_warns_and_clamps_when_a_clip_is_too_short():
    msgs = []
    shots = build_plan([FakeClip(40)], 24, 152, 30, warn=msgs.append)
    assert msgs and all("needs" in m for m in msgs)
    assert all(s["f0"] >= 0 for s in shots if "clip" in s)


def test_plan_is_quiet_when_clips_are_long_enough():
    msgs = []
    build_plan([FakeClip(900)], 24, 152, 30, warn=msgs.append)
    assert not msgs
