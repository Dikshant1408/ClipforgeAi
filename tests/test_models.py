from clipforge.models import Status, Segment, ClipMetadata, SourceChannel, VideoRecord

def test_status_values():
    assert Status.DISCOVERED == "DISCOVERED"
    assert Status.READY == "READY"
    assert Status.PUBLISHED == "PUBLISHED"
    assert len(list(Status)) == 14

def test_segment_defaults():
    s = Segment(start=1.0, end=2.5, score=0.9)
    assert s.reason == "" and s.end == 2.5

def test_source_channel_defaults():
    c = SourceChannel(name="Tarik", channel_id="UC1")
    assert c.enabled is True and c.priority == 100

def test_video_record_defaults():
    v = VideoRecord(video_id="v1", channel_id="UC1", channel_name="Tarik",
                    title="t", url="u", status=Status.DISCOVERED)
    assert v.retry_count == 0 and v.rank_score == 0.0
