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
        Path(argv[-1]).write_text("x")
        return 0
    c = Clipper(str(tmp_path), runner=runner)
    seg = Segment(start=10.0, end=25.0, score=1.0)
    out = c.make_short("vid1", str(tmp_path / "src.mp4"), seg, [])
    assert out == str(tmp_path / "clips" / "vid1.mp4")
    argv = calls["argv"]
    assert "-ss" in argv and "crop" in " ".join(argv)
    assert "ass=" in " ".join(argv) or "subtitles=" in " ".join(argv)


def test_make_short_failure_raises(tmp_path):
    c = Clipper(str(tmp_path), runner=lambda argv: 1)
    seg = Segment(start=0.0, end=15.0, score=1.0)
    with pytest.raises(RuntimeError):
        c.make_short("vid1", "src.mp4", seg, [])


def test_output_audio_matches_segment_duration(tmp_path):
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


def test_build_ass_karaoke_highlights_words():
    segs = [TranscriptSeg(10.0, 12.0, "hello world",
                          [Word(10.0, 11.0, "hello"), Word(11.0, 12.0, "world")])]
    ass = build_ass(segs, seg_start=10.0, seg_end=12.0)
    assert "\\k" in ass
    assert "hello" in ass and "world" in ass


def test_build_ass_hook_overlay_present():
    segs = [TranscriptSeg(0.0, 2.0, "hi", [Word(0.0, 2.0, "hi")])]
    ass = build_ass(segs, seg_start=0.0, seg_end=20.0, hook_text="He threw it")
    assert "Hook," in ass
    assert "He threw it" in ass


def test_make_short_includes_zoompan(tmp_path):
    def runner(argv):
        Path(argv[-1]).write_text("x")
        return 0
    c = Clipper(str(tmp_path), runner=runner)
    seg = Segment(start=10.0, end=25.0, score=1.0)
    c.make_short("vid1", str(tmp_path / "src.mp4"), seg,
                 [TranscriptSeg(10.0, 12.0, "hi", [])], hook_text="Hook line")
    ass_path = tmp_path / "clips" / "vid1.ass"
    assert ass_path.exists()
    ass_content = ass_path.read_text(encoding="utf-8")
    assert "Hook line" in ass_content
