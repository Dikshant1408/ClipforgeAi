from clipforge.monitor import parse_feed, feed_url, Monitor
from clipforge.db import Database
from clipforge.models import SourceChannel, Status

SAMPLE = """<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>First Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
    <published>2026-01-02T10:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>def456</yt:videoId>
    <title>Second Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=def456"/>
    <published>2026-01-01T10:00:00+00:00</published>
  </entry>
</feed>"""

def test_feed_url():
    assert feed_url("UC1") == \
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC1"

def test_parse_feed():
    items = parse_feed(SAMPLE)
    assert len(items) == 2
    assert items[0]["video_id"] == "abc123"
    assert items[0]["url"].endswith("v=abc123")
    assert items[0]["title"] == "First Video"

def test_poll_inserts_new_and_dedupes(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    mon = Monitor(db, fetch=lambda url: SAMPLE)
    ch = [SourceChannel(name="A", channel_id="UC1")]
    first = mon.poll(ch)
    assert set(first) == {"abc123", "def456"}
    second = mon.poll(ch)  # same feed again
    assert second == []
    assert db.get("abc123").status == Status.DISCOVERED

def test_poll_skips_disabled_not_passed(tmp_path):
    # poll only receives channels the caller already filtered
    db = Database(str(tmp_path / "t.db"))
    mon = Monitor(db, fetch=lambda url: SAMPLE)
    assert mon.poll([]) == []
