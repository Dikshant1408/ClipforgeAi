import pytest
from pathlib import Path
from clipforge.downloader import Downloader

def test_is_live_true():
    d = Downloader("s", info_fn=lambda u: {"is_live": True, "duration": 0})
    assert d.is_live("u") is True

def test_duration():
    d = Downloader("s", info_fn=lambda u: {"is_live": False, "duration": 123.0})
    assert d.duration("u") == 123.0

def test_download_success(tmp_path):
    calls = {}
    def runner(argv):
        calls["argv"] = argv
        return 0
    d = Downloader(str(tmp_path), runner=runner)
    out = d.download("vid1", "http://x")
    assert out == str(tmp_path / "videos" / "vid1.mp4")
    assert "http://x" in calls["argv"]
    assert (tmp_path / "videos").is_dir()

def test_download_failure_raises(tmp_path):
    d = Downloader(str(tmp_path), runner=lambda argv: 1)
    with pytest.raises(RuntimeError):
        d.download("vid1", "http://x")
