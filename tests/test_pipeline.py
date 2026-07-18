import pytest
from clipforge.pipeline import Pipeline
from clipforge.db import Database
from clipforge.models import Status, VideoRecord, Segment, ClipMetadata, SourceChannel
from clipforge.transcribe import TranscriptSeg
from clipforge.config import Config

def _cfg(tmp_path):
    return Config(
        source_channels=[SourceChannel("A", "UC1", True, 1)],
        publish_time="18:00", timezone="UTC", monitor_interval_minutes=10,
        clip_min_seconds=5, clip_max_seconds=30, crop="center",
        whisper_model="small", whisper_device="cpu",
        llm_provider="gemini", llm_model="m",
        youtube_privacy_status="public", youtube_category_id="20",
        storage_root=str(tmp_path), max_disk_gb=50, _path="x")

class FakeDownloader:
    def is_live(self, url): return False
    def duration(self, url): return 100.0
    def download(self, vid, url): return f"/src/{vid}.mp4"

class FakeTranscriber:
    def transcribe(self, v, a):
        return [TranscriptSeg(0.0, 10.0, "insane no way", [])]

class FakeClipper:
    def make_short(self, vid, src, seg, tr): return f"/clips/{vid}.mp4"

class FakeUploader:
    def __init__(self): self.uploaded = []
    def upload(self, clip_path, meta):
        self.uploaded.append((clip_path, meta))
        return "YTID"

class FakeCleanup:
    def __init__(self): self.deleted = []
    def delete_source(self, vid, src): self.deleted.append(vid)
    def enforce_quota(self): return 0

def _pipe(tmp_path, uploader=None):
    db = Database(str(tmp_path / "t.db"))
    return db, Pipeline(db, FakeDownloader(), FakeTranscriber(),
                        FakeClipper(), uploader or FakeUploader(),
                        FakeCleanup(), _cfg(tmp_path), llm=None)

def _seed(db, vid="v1"):
    db.insert_discovered(VideoRecord(vid, "UC1", "A", "t", "u",
                                     Status.DISCOVERED, discovered_at="2026-01-01"))

def test_advance_download(tmp_path):
    db, pipe = _pipe(tmp_path)
    _seed(db)
    assert pipe.advance_one() == "v1"
    assert db.get("v1").status == Status.DOWNLOADED

def test_advance_full_to_ready(tmp_path):
    db, pipe = _pipe(tmp_path)
    _seed(db)
    for _ in range(10):
        if pipe.advance_one() is None:
            break
    assert db.get("v1").status == Status.READY

def test_advance_none_when_idle(tmp_path):
    db, pipe = _pipe(tmp_path)
    assert pipe.advance_one() is None

def test_retry_then_fail(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    _seed(db)
    class Boom(FakeDownloader):
        def download(self, vid, url): raise RuntimeError("net")
    pipe = Pipeline(db, Boom(), FakeTranscriber(), FakeClipper(),
                    FakeUploader(), FakeCleanup(), _cfg(tmp_path))
    for _ in range(4):
        pipe.advance_one()
    assert db.get("v1").status == Status.FAILED

def test_skip_live_video(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    _seed(db)
    class Live(FakeDownloader):
        def is_live(self, url): return True
    pipe = Pipeline(db, Live(), FakeTranscriber(), FakeClipper(),
                    FakeUploader(), FakeCleanup(), _cfg(tmp_path))
    for _ in range(4):
        pipe.advance_one()
    assert db.get("v1").status == Status.FAILED

def test_publish_daily_uploads_top_ranked(tmp_path):
    up = FakeUploader()
    db, pipe = _pipe(tmp_path, uploader=up)
    for vid, rank in [("v1", 0.2), ("v2", 0.9)]:
        _seed(db, vid)
        db.set_status(vid, Status.READY)
        db.set_rank(vid, rank)
        db.set_paths(vid, source_path=f"/src/{vid}.mp4", clip_path=f"/c/{vid}.mp4")
    published = pipe.publish_daily()
    assert published == "v2"
    assert db.get("v2").status == Status.PUBLISHED
    assert len(up.uploaded) == 1

def test_publish_daily_none_when_empty(tmp_path):
    db, pipe = _pipe(tmp_path)
    assert pipe.publish_daily() is None
