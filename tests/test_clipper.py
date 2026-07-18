import pytest
from pathlib import Path
from clipforge.clipper import format_timestamp, build_ass, Clipper
from clipforge.models import Segment
from clipforge.transcribe import TranscriptSeg, Word

def test_format_timestamp():
    assert format_timestamp(0) == "0:00:00.00"
    assert format_timestamp(3661.5) == "1:01:01.50"

def test_build_ass_rebases_time():
    segs = [TranscriptSeg(10.0, 12.0, "hello", [Word(10.0, 11.0, "hello")])]
    ass = build_ass(segs, seg_start=10.0, seg_end=12.0)
    assert "Dialogue:" in ass
    assert "0:00:00.00" in ass  # 10.0 rebased to 0
    assert "hello" in ass

def test_make_short_builds_ffmpeg(tmp_path):
    calls = {}
    def runner(argv):
        calls["argv"] = argv
        Path(argv[-1]).write_text("x")  # simulate output creation
        return 0
    c = Clipper(str(tmp_path), runner=runner)
    seg = Segment(start=10.0, end=25.0, score=1.0)
    segs = [TranscriptSeg(10.0, 12.0, "hi", [Word(10.0, 11.0, "hi")])]
    out = c.make_short("vid1", str(tmp_path / "src.mp4"), seg, segs)
    assert out == str(tmp_path / "clips" / "vid1.mp4")
    argv = calls["argv"]
    assert "-ss" in argv and "crop" in " ".join(argv)
    assert "ass=" in " ".join(argv) or "subtitles=" in " ".join(argv)

def test_make_short_failure_raises(tmp_path):
    c = Clipper(str(tmp_path), runner=lambda argv: 1)
    seg = Segment(start=0.0, end=15.0, score=1.0)
    with pytest.raises(RuntimeError):
        c.make_short("vid1", "src.mp4", seg, [])
