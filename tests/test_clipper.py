import pytest
from pathlib import Path
from clipforge.clipper import Clipper
from clipforge.models import Segment


def test_make_short_builds_ffmpeg(tmp_path):
    calls = {}
    def runner(argv):
        calls["argv"] = argv
        Path(argv[-1]).write_text("x")
        return 0
    c = Clipper(str(tmp_path), runner=runner)
    seg = Segment(start=10.0, end=25.0, score=1.0)
    out = c.make_short("vid1", str(tmp_path / "src.mp4"), seg, [])
    assert out == str(tmp_path / "clips" / "vid1.mp4")
    argv = calls["argv"]
    assert "-ss" in argv and "crop" in " ".join(argv)
    assert "ass=" not in " ".join(argv)  # no burned subtitles


def test_make_short_failure_raises(tmp_path):
    c = Clipper(str(tmp_path), runner=lambda argv: 1)
    seg = Segment(start=0.0, end=15.0, score=1.0)
    with pytest.raises(RuntimeError):
        c.make_short("vid1", "src.mp4", seg, [])


def test_output_audio_matches_segment_duration(tmp_path):
    """Regression: input-side -ss desynced audio and cut it short. Output must
    contain both video and audio streams whose duration matches the segment."""
    import subprocess as _sp
    src = tmp_path / "src.mp4"
    _sp.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=30:size=1280x720:rate=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
             "-c:v", "libx264", "-c:a", "aac", "-shortest",
             "-pix_fmt", "yuv420p", str(src)], capture_output=True)
    seg = Segment(start=5.0, end=20.0, score=1.0)
    out = Clipper(str(tmp_path)).make_short("v1", str(src), seg, [])
    probe = _sp.run(["ffprobe", "-v", "error",
                    "-show_entries", "format=duration:stream=codec_type",
                    "-of", "json", str(out)], capture_output=True, text=True)
    data = __import__("json").loads(probe.stdout)
    dur = float(data["format"]["duration"])
    types = [s["codec_type"] for s in data["streams"]]
    assert "video" in types and "audio" in types
    assert 14.5 <= dur <= 15.5
