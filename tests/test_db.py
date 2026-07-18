import pytest
from clipforge.db import Database
from clipforge.models import Status, VideoRecord

def _rec(vid, prio_ts="2026-01-01T00:00:00"):
    return VideoRecord(video_id=vid, channel_id="UC1", channel_name="A",
                       title="t", url="u", status=Status.DISCOVERED,
                       discovered_at=prio_ts)

@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))

def test_insert_and_dedupe(db):
    assert db.insert_discovered(_rec("v1")) is True
    assert db.insert_discovered(_rec("v1")) is False
    assert db.exists("v1") is True

def test_status_transition(db):
    db.insert_discovered(_rec("v1"))
    db.set_status("v1", Status.DOWNLOADED)
    assert db.get("v1").status == Status.DOWNLOADED

def test_bump_retry(db):
    db.insert_discovered(_rec("v1"))
    assert db.bump_retry("v1", "boom") == 1
    assert db.bump_retry("v1", "boom") == 2
    assert db.get("v1").last_error == "boom"

def test_next_in_status_oldest_first(db):
    db.insert_discovered(_rec("v2", "2026-01-02T00:00:00"))
    db.insert_discovered(_rec("v1", "2026-01-01T00:00:00"))
    assert db.next_in_status(Status.DISCOVERED).video_id == "v1"

def test_list_ready_ordered_by_rank(db):
    for v in ("v1", "v2"):
        db.insert_discovered(_rec(v))
        db.set_status(v, Status.READY)
    db.set_rank("v1", 0.5)
    db.set_rank("v2", 0.9)
    assert [r.video_id for r in db.list_ready()] == ["v2", "v1"]

def test_reset_stuck(db):
    db.insert_discovered(_rec("v1"))
    db.set_status("v1", Status.DOWNLOADING)
    assert db.reset_stuck() == 1
    assert db.get("v1").status == Status.DISCOVERED
