import shutil
import subprocess

import pytest

from reel import audio, checks
from reel.render import render_reel

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _make_clip(path, seconds, freq):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(path)], check=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    out = []
    for i, (sec, f) in enumerate(((3, 440), (2, 660))):
        p = d / f"c{i}.mp4"
        _make_clip(p, sec, f)
        out.append(str(p))
    return out


def test_minimal_reel(clips, tmp_path):
    res = render_reel(clips, tmp_path / "r.mp4", {"beats": 12}, size=(270, 480),
                      work_dir=tmp_path / "w", log=lambda m: None)
    failed = [c for c in res["checks"] if not c[1]]
    assert not failed, failed
    assert res["frames"] > 0 and (tmp_path / "r.mp4").stat().st_size > 1000


def test_full_featured_reel(clips, tmp_path):
    spec = {"beats": 16, "title": "标题", "subtitle": "TAG", "transition": "zoom",
            "captions": [{"layout": "bloom", "text": "铁水成花", "tag": "T", "at": "brk"},
                         {"layout": "grand", "text": "火树银花", "at": "fin"}],
            "effects": [{"name": "glitch", "from": 4, "to": 10, "mode": "beat", "amt": 0.7},
                        {"name": "vhs", "from": 0, "to": 16, "mode": "always", "amt": 0.3}]}
    res = render_reel(clips[:1], tmp_path / "f.mp4", spec, size=(270, 480),
                      work_dir=tmp_path / "w", log=lambda m: None)
    assert all(c[1] for c in res["checks"]), res["checks"]


def test_bgm_none_still_has_audio_track(clips, tmp_path):
    res = render_reel(clips, tmp_path / "n.mp4", {"beats": 12, "bgm": "none"}, size=(270, 480),
                      work_dir=tmp_path / "w", log=lambda m: None)
    assert checks.probe(res["path"])["audio"]


def _voice_file(path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.2",
                    str(path)], check=True)
    return str(path)


def test_voiceover_from_local_file_is_ducked(clips, tmp_path):
    spec = {"beats": 16, "voiceover": [{"file": _voice_file(tmp_path / "v.wav"), "at": "s2"}]}
    res = render_reel(clips, tmp_path / "v.mp4", spec, size=(270, 480), work_dir=tmp_path / "w", log=lambda m: None)
    assert all(c[1] for c in res["checks"]), res["checks"]


@pytest.mark.skipif(not audio.say_available(), reason="needs macOS `say`")
def test_voiceover_with_say(clips, tmp_path):
    spec = {"beats": 16, "tts": "say", "voiceover": [{"text": "铁花落下", "at": "s2"}]}
    res = render_reel(clips, tmp_path / "s.mp4", spec, size=(270, 480), work_dir=tmp_path / "w", log=lambda m: None)
    assert all(c[1] for c in res["checks"]), res["checks"]


def test_overlapping_voiceovers_are_rejected(clips, tmp_path):
    f = _voice_file(tmp_path / "v.wav")
    spec = {"beats": 16, "voiceover": [{"file": f, "at": "s2"}, {"file": f, "at": "s2", "offset": 0.3}]}
    with pytest.raises(ValueError, match="overlaps"):
        render_reel(clips, tmp_path / "o.mp4", spec, size=(270, 480), work_dir=tmp_path / "w", log=lambda m: None)


def test_look_night_and_sans_typeface(clips, tmp_path):
    spec = {"beats": 12, "look": "night", "typeface": "sans", "title": "标题", "subtitle": "TAG"}
    res = render_reel(clips[:1], tmp_path / "n.mp4", spec, size=(270, 480), work_dir=tmp_path / "w", log=lambda m: None)
    assert all(c[1] for c in res["checks"]), res["checks"]


def test_decode_cache_follows_output_size_and_clip_limit(clips, tmp_path):
    render_reel(clips[:1], tmp_path / "c.mp4", {"beats": 12}, size=(270, 480), work_dir=tmp_path / "w",
                max_clip_seconds=1, log=lambda m: None)
    cache = [p for p in (tmp_path / "w").iterdir() if p.suffix == ".u8"]
    assert len(cache) == 1
    assert cache[0].stat().st_size == 30 * 480 * 270 * 3     # 1 s at 30 fps, long edge 480 (source is 16:9)


def test_bad_inputs(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_reel([str(tmp_path / "missing.mp4")], tmp_path / "x.mp4", {}, size=(270, 480))
    with pytest.raises(ValueError):
        render_reel([], tmp_path / "x.mp4", {}, size=(270, 480))
    with pytest.raises(ValueError):
        render_reel(["a.mp4"], tmp_path / "x.mp4", {"beats": 2}, size=(270, 480))


def test_preflight_fails_before_any_rendering(clips, tmp_path):
    work = tmp_path / "w"
    with pytest.raises(FileNotFoundError, match="bgm file not found"):
        render_reel(clips, tmp_path / "x.mp4", {"bgm": str(tmp_path / "nope.mp3")}, size=(270, 480), work_dir=work)
    silent = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", str(silent)], check=True)
    with pytest.raises(ValueError, match="no audio stream"):
        render_reel(clips, tmp_path / "x.mp4", {"bgm": str(silent)}, size=(270, 480), work_dir=work)
    assert not list(work.glob("*.u8")), "nothing may be decoded before the checks pass"
