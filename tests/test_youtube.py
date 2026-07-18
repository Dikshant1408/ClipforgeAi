import pytest
from clipforge.youtube import YouTubeUploader
from clipforge.models import ClipMetadata

class FakeInsert:
    def __init__(self, store):
        self._store = store
    def execute(self):
        return {"id": "NEWVIDEOID"}

class FakeVideos:
    def __init__(self, store):
        self._store = store
    def insert(self, part, body, media_body):
        self._store["part"] = part
        self._store["body"] = body
        return FakeInsert(self._store)

class FakeService:
    def __init__(self, store):
        self._store = store
    def videos(self):
        return FakeVideos(self._store)

def test_upload_returns_id():
    store = {}
    up = YouTubeUploader("public", "20",
                         service_factory=lambda: FakeService(store),
                         media_factory=lambda p: object())
    meta = ClipMetadata(title="T", description="D", tags=["a"])
    vid = up.upload("clip.mp4", meta)
    assert vid == "NEWVIDEOID"
    assert store["body"]["snippet"]["title"] == "T"
    assert store["body"]["status"]["privacyStatus"] == "public"

def test_upload_appends_shorts_hashtag():
    store = {}
    up = YouTubeUploader("public", "20",
                         service_factory=lambda: FakeService(store),
                         media_factory=lambda p: object())
    up.upload("c.mp4", ClipMetadata(title="T", description="hello", tags=[]))
    assert "#Shorts" in store["body"]["snippet"]["description"]

def test_upload_error_raises():
    class BadInsert:
        def execute(self):
            raise Exception("api down")
    class BadVideos:
        def insert(self, **k):
            return BadInsert()
    class BadService:
        def videos(self):
            return BadVideos()
    up = YouTubeUploader("public", "20",
                         service_factory=lambda: BadService(),
                         media_factory=lambda p: object())
    with pytest.raises(RuntimeError):
        up.upload("c.mp4", ClipMetadata(title="T", description="D", tags=[]))
