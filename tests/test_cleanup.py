from pathlib import Path
from clipforge.cleanup import Cleanup, dir_size_gb
from clipforge.db import Database
from clipforge.models import Status, VideoRecord

def _rec(vid, ts):
    return VideoRecord(video_id=vid, channel_id="UC1", channel_name="A",
                       title="t", url="u", status=Status.DISCOVERED,
                       discovered_at=ts)

def test_dir_size_gb(tmp_path):
    (tmp_path / "f.bin").write_bytes(b"0" * 1024)
    assert dir_size_gb(str(tmp_path)) > 0

def test_delete_source_safe_when_missing(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    c = Cleanup(db, str(tmp_path), max_disk_gb=50)
    c.delete_source("v1", str(tmp_path / "nope.mp4"))  # no raise

def test_delete_source_removes_file(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    f = tmp_path / "s.mp4"
    f.write_text("x")
    c = Cleanup(db, str(tmp_path), max_disk_gb=50)
    c.delete_source("v1", str(f))
    assert not f.exists()

def test_enforce_quota_deletes_oldest_published(tmp_path):
    root = tmp_path
    vids = root / "videos"
    vids.mkdir()
    db = Database(str(root / "t.db"))
    big = b"0" * (2 * 1024 * 1024)  # 2MB each
    for vid, ts in [("v1", "2026-01-01"), ("v2", "2026-01-02")]:
        p = vids / f"{vid}.mp4"
        p.write_bytes(big)
        db.insert_discovered(_rec(vid, ts))
        db.set_status(vid, Status.PUBLISHED)
        db.set_paths(vid, source_path=str(p))
    c = Cleanup(db, str(root), max_disk_gb=0)  # force over-quota
    deleted = c.enforce_quota()
    assert deleted >= 1
    assert not (vids / "v1.mp4").exists()  # oldest removed first
