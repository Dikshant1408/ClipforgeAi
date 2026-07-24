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


def test_delete_video_files_removes_all(tmp_path):
    root = tmp_path
    db = Database(str(root / "t.db"))
    
    videos_dir = root / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    video_file = videos_dir / "v1.mp4"
    video_file.write_text("v")
    
    clips_dir = root / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_file = clips_dir / "v1.mp4"
    clip_file.write_text("c")
    
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / "v1.wav"
    audio_file.write_text("a")
    
    c = Cleanup(db, str(root), max_disk_gb=50)
    c.delete_video_files("v1", str(video_file), str(clip_file))
    
    assert not video_file.exists()
    assert not clip_file.exists()
    assert not audio_file.exists()


def test_cleanup_expired_files_processes_correctly(tmp_path):
    import datetime
    root = tmp_path
    db = Database(str(root / "t.db"))
    
    now = datetime.datetime.now(datetime.timezone.utc)
    ready_old = (now - datetime.timedelta(days=3)).isoformat()
    ready_new = (now - datetime.timedelta(days=1)).isoformat()
    pub_old = (now - datetime.timedelta(days=8)).isoformat()
    pub_new = (now - datetime.timedelta(days=5)).isoformat()
    
    vids = root / "videos"
    clips = root / "clips"
    vids.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    
    for vid, status, ts in [
        ("r_old", Status.READY, ready_old),
        ("r_new", Status.READY, ready_new),
        ("p_old", Status.PUBLISHED, pub_old),
        ("p_new", Status.PUBLISHED, pub_new)
    ]:
        v_file = vids / f"{vid}.mp4"
        c_file = clips / f"{vid}.mp4"
        v_file.write_text("v")
        c_file.write_text("c")
        
        rec = VideoRecord(video_id=vid, channel_id="UC1", channel_name="A",
                          title="t", url="u", status=status,
                          discovered_at=ts)
        db.insert_discovered(rec)
        db.set_status(vid, status)
        db.set_paths(vid, source_path=str(v_file), clip_path=str(c_file))
        
    c = Cleanup(db, str(root), max_disk_gb=50)
    c.cleanup_expired_files()
    
    assert not (vids / "r_old.mp4").exists()
    assert not (clips / "r_old.mp4").exists()
    rec_r_old = db.get("r_old")
    assert rec_r_old.source_path == ""
    assert rec_r_old.clip_path == ""
    
    assert (vids / "r_new.mp4").exists()
    assert (clips / "r_new.mp4").exists()
    
    assert not (vids / "p_old.mp4").exists()
    assert not (clips / "p_old.mp4").exists()
    rec_p_old = db.get("p_old")
    assert rec_p_old.source_path == ""
    assert rec_p_old.clip_path == ""
    
    assert (vids / "p_new.mp4").exists()
    assert (clips / "p_new.mp4").exists()
