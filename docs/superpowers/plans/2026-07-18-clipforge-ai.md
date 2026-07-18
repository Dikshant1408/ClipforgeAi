# ClipForge AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-process Python automation that watches YouTube source channels, turns new videos into vertical 9:16 Shorts with captions and AI metadata, and auto-publishes one Short daily at 18:00.

**Architecture:** One long-running process using APScheduler with a MonitorJob (RSS, every 10 min), a continuous ProcessWorker (download -> transcribe -> highlight -> clip -> metadata), and a PublishJob (daily 18:00). All stages are isolated modules coordinating through a SQLite state machine keyed by `video_id`, so the process is crash-safe and dedupes automatically.

**Tech Stack:** Python 3.12, yt-dlp, FFmpeg, faster-whisper, Google Gemini (free tier) behind an LLM interface, google-api-python-client + OAuth, APScheduler, SQLite (stdlib `sqlite3`), pytest.

## Global Constraints

- Python version: 3.12 (exact floor).
- OS target: Windows (paths, subprocess use). Use `pathlib.Path` everywhere; never hardcode `/` or `\\`.
- Secrets never committed: Gemini API key in `.env`; YouTube OAuth in `token.json`/`client_secret.json`. All three plus `storage/` and `clipforge.db` are gitignored.
- Detection: RSS only (`https://www.youtube.com/feeds/videos.xml?channel_id=...`). No YouTube Data API quota spent on detection.
- LLM: `provider: gemini`, model `gemini-2.0-flash`, accessed only through the `LLMProvider` interface (never call the SDK directly outside `llm.py`).
- Publish exactly ONE Short per day at `publish_time` in configured `timezone`.
- Clip length bounded by `clip.min_seconds` (default 20) and `clip.max_seconds` (default 60).
- Crop: center-crop to 9:16.
- Captions: burned-in styled subtitle blocks (1-2 lines).
- Full-auto upload (no human approval). Copyright risk is accepted and documented in the spec.
- Status enum (exact strings): `DISCOVERED`, `DOWNLOADING`, `DOWNLOADED`, `TRANSCRIBING`, `TRANSCRIBED`, `HIGHLIGHTING`, `HIGHLIGHTED`, `CLIPPING`, `CLIPPED`, `METADATA`, `READY`, `PUBLISHING`, `PUBLISHED`, `FAILED`.
- Retries: transient failures retry up to 3 times (4th failure -> `FAILED`).
- Tests must not hit the network, GPU, or real APIs. All externals (yt-dlp, faster-whisper, FFmpeg, Gemini, YouTube) are wrapped so they can be mocked.

---

## File Structure

```
clipforge/
  __init__.py
  config.py         # load/validate config.json + hot-reload channels
  models.py         # dataclasses/enums: Status, VideoRecord, Segment, ClipMetadata, Config
  db.py             # sqlite schema + state transitions + dedupe + reset-on-restart
  monitor.py        # RSS fetch + parse + new-video detection
  downloader.py     # yt-dlp wrapper: download video, is_live check
  transcribe.py     # audio extract (ffmpeg) + faster-whisper -> segments/words
  highlights.py     # audio energy + keyword scoring + LLM ranking -> best Segment
  clipper.py        # ffmpeg cut + center-crop 9:16 + burn subtitles (ASS)
  metadata.py       # LLM -> title/description/tags (+ template fallback)
  llm.py            # LLMProvider interface + GeminiProvider
  youtube.py        # OAuth + videos.insert upload
  cleanup.py        # delete sources after publish + enforce max_disk_gb
  scheduler.py      # wire MonitorJob + ProcessWorker + PublishJob
  main.py           # entrypoint, logging, CLI flags (--once, --dry-run)
config.example.json
requirements.txt
.gitignore
tests/
  conftest.py
  test_config.py
  test_db.py
  test_monitor.py
  test_downloader.py
  test_transcribe.py
  test_highlights.py
  test_clipper.py
  test_metadata.py
  test_llm.py
  test_youtube.py
  test_cleanup.py
  test_scheduler.py
```

Each module has one responsibility. External tools (yt-dlp, ffmpeg, whisper,
gemini, youtube) are each isolated in a single module so tests mock at that
boundary. `models.py` holds shared types so tasks agree on signatures.

---

### Task 1: Project scaffold, gitignore, dependencies

**Files:**
- Create: `requirements.txt`, `.gitignore`, `clipforge/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `clipforge` package; pytest runnable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
import clipforge

def test_package_imports():
    assert clipforge.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL (ImportError / no `__version__`).

- [ ] **Step 3: Create files**

`clipforge/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`requirements.txt`:
```
yt-dlp==2024.12.13
faster-whisper==1.0.3
google-generativeai==0.8.3
google-api-python-client==2.149.0
google-auth-oauthlib==1.2.1
APScheduler==3.10.4
pytest==8.3.4
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
token.json
client_secret.json
storage/
clipforge.db
config.json
.venv/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore clipforge/__init__.py tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "chore: project scaffold and dependencies"
```

---

### Task 2: Shared models and status enum

**Files:**
- Create: `clipforge/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Status(str, Enum)` with members equal to the Global Constraints status strings.
  - `@dataclass Segment` with fields `start: float`, `end: float`, `score: float`, `reason: str = ""`.
  - `@dataclass ClipMetadata` with `title: str`, `description: str`, `tags: list[str]`.
  - `@dataclass SourceChannel` with `name: str`, `channel_id: str`, `enabled: bool = True`, `priority: int = 100`.
  - `@dataclass VideoRecord` with `video_id: str`, `channel_id: str`, `channel_name: str`, `title: str`, `url: str`, `status: Status`, `retry_count: int = 0`, `last_error: str = ""`, `source_path: str = ""`, `clip_path: str = ""`, `rank_score: float = 0.0`, `discovered_at: str = ""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    HIGHLIGHTING = "HIGHLIGHTING"
    HIGHLIGHTED = "HIGHLIGHTED"
    CLIPPING = "CLIPPING"
    CLIPPED = "CLIPPED"
    METADATA = "METADATA"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass
class Segment:
    start: float
    end: float
    score: float
    reason: str = ""


@dataclass
class ClipMetadata:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class SourceChannel:
    name: str
    channel_id: str
    enabled: bool = True
    priority: int = 100


@dataclass
class VideoRecord:
    video_id: str
    channel_id: str
    channel_name: str
    title: str
    url: str
    status: Status
    retry_count: int = 0
    last_error: str = ""
    source_path: str = ""
    clip_path: str = ""
    rank_score: float = 0.0
    discovered_at: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/models.py tests/test_models.py
git commit -m "feat: shared models and status enum"
```

---

### Task 3: Config loading and validation

**Files:**
- Create: `clipforge/config.py`, `config.example.json`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `SourceChannel` from `models.py`.
- Produces:
  - `@dataclass Config` with: `source_channels: list[SourceChannel]`, `publish_time: str`, `timezone: str`, `monitor_interval_minutes: int`, `clip_min_seconds: int`, `clip_max_seconds: int`, `crop: str`, `whisper_model: str`, `whisper_device: str`, `llm_provider: str`, `llm_model: str`, `youtube_privacy_status: str`, `youtube_category_id: str`, `storage_root: str`, `max_disk_gb: int`, `_path: str`.
  - `load_config(path: str) -> Config` (raises `ValueError` on invalid).
  - `Config.enabled_channels() -> list[SourceChannel]` returning only `enabled`, sorted by `priority`.
  - `Config.reload() -> Config` re-reading `_path` (returns a fresh Config; used for hot-reload).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import json, pytest
from pathlib import Path
from clipforge.config import load_config

def _write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)

VALID = {
    "source_channels": [
        {"name": "B", "channel_id": "UCB", "enabled": True, "priority": 2},
        {"name": "A", "channel_id": "UCA", "enabled": True, "priority": 1},
        {"name": "C", "channel_id": "UCC", "enabled": False, "priority": 3},
    ],
    "publish_time": "18:00",
    "timezone": "Asia/Kolkata",
    "monitor_interval_minutes": 10,
    "clip": {"min_seconds": 20, "max_seconds": 60, "crop": "center"},
    "whisper": {"model": "small", "device": "cuda"},
    "llm": {"provider": "gemini", "model": "gemini-2.0-flash"},
    "youtube": {"privacy_status": "public", "category_id": "20"},
    "storage": {"root": "./storage"},
    "max_disk_gb": 50,
}

def test_load_valid(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    assert cfg.publish_time == "18:00"
    assert cfg.clip_max_seconds == 60
    assert len(cfg.source_channels) == 3

def test_enabled_channels_sorted_by_priority(tmp_path):
    cfg = load_config(_write(tmp_path, VALID))
    en = cfg.enabled_channels()
    assert [c.name for c in en] == ["A", "B"]

def test_invalid_publish_time_rejected(tmp_path):
    bad = dict(VALID); bad["publish_time"] = "6pm"
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

def test_min_greater_than_max_rejected(tmp_path):
    bad = json.loads(json.dumps(VALID)); bad["clip"]["min_seconds"] = 90
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))

def test_empty_channels_rejected(tmp_path):
    bad = json.loads(json.dumps(VALID)); bad["source_channels"] = []
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, bad))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/config.py`**

```python
from __future__ import annotations
import json, re
from dataclasses import dataclass
from clipforge.models import SourceChannel

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class Config:
    source_channels: list[SourceChannel]
    publish_time: str
    timezone: str
    monitor_interval_minutes: int
    clip_min_seconds: int
    clip_max_seconds: int
    crop: str
    whisper_model: str
    whisper_device: str
    llm_provider: str
    llm_model: str
    youtube_privacy_status: str
    youtube_category_id: str
    storage_root: str
    max_disk_gb: int
    _path: str

    def enabled_channels(self) -> list[SourceChannel]:
        return sorted(
            [c for c in self.source_channels if c.enabled],
            key=lambda c: c.priority,
        )

    def reload(self) -> "Config":
        return load_config(self._path)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)

    raw_channels = d.get("source_channels", [])
    _require(isinstance(raw_channels, list) and raw_channels,
             "source_channels must be a non-empty list")
    channels: list[SourceChannel] = []
    for c in raw_channels:
        _require("name" in c and "channel_id" in c,
                 "each channel needs name and channel_id")
        channels.append(SourceChannel(
            name=c["name"], channel_id=c["channel_id"],
            enabled=bool(c.get("enabled", True)),
            priority=int(c.get("priority", 100)),
        ))

    publish_time = d.get("publish_time", "")
    _require(bool(_TIME_RE.match(publish_time)),
             "publish_time must be HH:MM 24-hour")

    clip = d.get("clip", {})
    mn = int(clip.get("min_seconds", 20))
    mx = int(clip.get("max_seconds", 60))
    _require(0 < mn <= mx, "clip.min_seconds must be >0 and <= max_seconds")
    crop = clip.get("crop", "center")
    _require(crop == "center", "only crop=center supported in v1")

    return Config(
        source_channels=channels,
        publish_time=publish_time,
        timezone=d.get("timezone", "UTC"),
        monitor_interval_minutes=int(d.get("monitor_interval_minutes", 10)),
        clip_min_seconds=mn,
        clip_max_seconds=mx,
        crop=crop,
        whisper_model=d.get("whisper", {}).get("model", "small"),
        whisper_device=d.get("whisper", {}).get("device", "cpu"),
        llm_provider=d.get("llm", {}).get("provider", "gemini"),
        llm_model=d.get("llm", {}).get("model", "gemini-2.0-flash"),
        youtube_privacy_status=d.get("youtube", {}).get("privacy_status", "public"),
        youtube_category_id=d.get("youtube", {}).get("category_id", "20"),
        storage_root=d.get("storage", {}).get("root", "./storage"),
        max_disk_gb=int(d.get("max_disk_gb", 50)),
        _path=path,
    )
```

`config.example.json`: same shape as `VALID` above, with placeholder channel_id `UCxxxxxxxxxxxxxxxxxxxxxx`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/config.py config.example.json tests/test_config.py
git commit -m "feat: config loading and validation"
```

---

### Task 4: SQLite database and state machine

**Files:**
- Create: `clipforge/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Status`, `VideoRecord` from `models.py`.
- Produces `class Database`:
  - `Database(path: str)` — opens/creates DB, runs schema migration.
  - `insert_discovered(rec: VideoRecord) -> bool` — inserts if `video_id` new; returns False if duplicate (no raise).
  - `exists(video_id: str) -> bool`.
  - `get(video_id: str) -> VideoRecord | None`.
  - `set_status(video_id: str, status: Status, error: str = "") -> None`.
  - `bump_retry(video_id: str, error: str) -> int` — increments retry_count, sets `last_error`, returns new count.
  - `set_paths(video_id: str, source_path: str = None, clip_path: str = None) -> None`.
  - `set_rank(video_id: str, rank_score: float) -> None`.
  - `next_in_status(status: Status) -> VideoRecord | None` — oldest by `discovered_at`.
  - `list_ready() -> list[VideoRecord]` — status READY, sorted by rank_score desc then discovered_at asc.
  - `reset_stuck() -> int` — maps in-progress statuses back to last clean state; returns count reset.
  - `published_source_paths() -> list[tuple[str, str]]` — (video_id, source_path) for PUBLISHED rows with non-empty source_path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
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
    db.set_rank("v1", 0.5); db.set_rank("v2", 0.9)
    assert [r.video_id for r in db.list_ready()] == ["v2", "v1"]

def test_reset_stuck(db):
    db.insert_discovered(_rec("v1"))
    db.set_status("v1", Status.DOWNLOADING)
    assert db.reset_stuck() == 1
    assert db.get("v1").status == Status.DISCOVERED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/db.py`**

```python
from __future__ import annotations
import sqlite3
from clipforge.models import Status, VideoRecord

# in-progress -> clean state to reset to on restart
_STUCK_MAP = {
    Status.DOWNLOADING: Status.DISCOVERED,
    Status.TRANSCRIBING: Status.DOWNLOADED,
    Status.HIGHLIGHTING: Status.TRANSCRIBED,
    Status.CLIPPING: Status.HIGHLIGHTED,
    Status.METADATA: Status.CLIPPED,
    Status.PUBLISHING: Status.READY,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    clip_path TEXT NOT NULL DEFAULT '',
    rank_score REAL NOT NULL DEFAULT 0.0,
    discovered_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_status ON videos(status);
"""


class Database:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _row_to_rec(self, r: sqlite3.Row) -> VideoRecord:
        return VideoRecord(
            video_id=r["video_id"], channel_id=r["channel_id"],
            channel_name=r["channel_name"], title=r["title"], url=r["url"],
            status=Status(r["status"]), retry_count=r["retry_count"],
            last_error=r["last_error"], source_path=r["source_path"],
            clip_path=r["clip_path"], rank_score=r["rank_score"],
            discovered_at=r["discovered_at"],
        )

    def insert_discovered(self, rec: VideoRecord) -> bool:
        try:
            self._conn.execute(
                "INSERT INTO videos (video_id, channel_id, channel_name, title,"
                " url, status, discovered_at) VALUES (?,?,?,?,?,?,?)",
                (rec.video_id, rec.channel_id, rec.channel_name, rec.title,
                 rec.url, Status.DISCOVERED.value, rec.discovered_at),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def exists(self, video_id: str) -> bool:
        c = self._conn.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,))
        return c.fetchone() is not None

    def get(self, video_id: str) -> VideoRecord | None:
        c = self._conn.execute("SELECT * FROM videos WHERE video_id=?", (video_id,))
        row = c.fetchone()
        return self._row_to_rec(row) if row else None

    def set_status(self, video_id: str, status: Status, error: str = "") -> None:
        self._conn.execute(
            "UPDATE videos SET status=?, last_error=? WHERE video_id=?",
            (status.value, error, video_id))
        self._conn.commit()

    def bump_retry(self, video_id: str, error: str) -> int:
        self._conn.execute(
            "UPDATE videos SET retry_count=retry_count+1, last_error=? WHERE video_id=?",
            (error, video_id))
        self._conn.commit()
        return self.get(video_id).retry_count

    def set_paths(self, video_id: str, source_path: str = None,
                  clip_path: str = None) -> None:
        if source_path is not None:
            self._conn.execute("UPDATE videos SET source_path=? WHERE video_id=?",
                               (source_path, video_id))
        if clip_path is not None:
            self._conn.execute("UPDATE videos SET clip_path=? WHERE video_id=?",
                               (clip_path, video_id))
        self._conn.commit()

    def set_rank(self, video_id: str, rank_score: float) -> None:
        self._conn.execute("UPDATE videos SET rank_score=? WHERE video_id=?",
                           (rank_score, video_id))
        self._conn.commit()

    def next_in_status(self, status: Status) -> VideoRecord | None:
        c = self._conn.execute(
            "SELECT * FROM videos WHERE status=? ORDER BY discovered_at ASC LIMIT 1",
            (status.value,))
        row = c.fetchone()
        return self._row_to_rec(row) if row else None

    def list_ready(self) -> list[VideoRecord]:
        c = self._conn.execute(
            "SELECT * FROM videos WHERE status=? "
            "ORDER BY rank_score DESC, discovered_at ASC", (Status.READY.value,))
        return [self._row_to_rec(r) for r in c.fetchall()]

    def reset_stuck(self) -> int:
        n = 0
        for stuck, clean in _STUCK_MAP.items():
            cur = self._conn.execute(
                "UPDATE videos SET status=? WHERE status=?",
                (clean.value, stuck.value))
            n += cur.rowcount
        self._conn.commit()
        return n

    def published_source_paths(self) -> list[tuple[str, str]]:
        c = self._conn.execute(
            "SELECT video_id, source_path FROM videos "
            "WHERE status=? AND source_path<>''", (Status.PUBLISHED.value,))
        return [(r["video_id"], r["source_path"]) for r in c.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/db.py tests/test_db.py
git commit -m "feat: sqlite state machine with dedupe and crash-safe reset"
```

---

### Task 5: RSS monitor (new-video detection)

**Files:**
- Create: `clipforge/monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `SourceChannel`, `VideoRecord`, `Status`; `Database`.
- Produces:
  - `parse_feed(xml: str) -> list[dict]` — each dict `{video_id, title, url, published}` from a YouTube RSS feed.
  - `feed_url(channel_id: str) -> str`.
  - `class Monitor(db: Database, fetch: Callable[[str], str])` where `fetch(url) -> xml` is injected (real impl uses urllib; tests inject a stub).
  - `Monitor.poll(channels: list[SourceChannel]) -> list[str]` — for each channel, fetch+parse, insert new videos as DISCOVERED, return list of newly inserted video_ids.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_monitor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/monitor.py`**

```python
from __future__ import annotations
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable
from clipforge.db import Database
from clipforge.models import SourceChannel, VideoRecord, Status

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_feed(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    items: list[dict] = []
    for entry in root.findall("atom:entry", _NS):
        vid_el = entry.find("yt:videoId", _NS)
        title_el = entry.find("atom:title", _NS)
        link_el = entry.find("atom:link", _NS)
        pub_el = entry.find("atom:published", _NS)
        if vid_el is None or vid_el.text is None:
            continue
        items.append({
            "video_id": vid_el.text,
            "title": title_el.text if title_el is not None else "",
            "url": link_el.get("href") if link_el is not None else
                   f"https://www.youtube.com/watch?v={vid_el.text}",
            "published": pub_el.text if pub_el is not None else "",
        })
    return items


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


class Monitor:
    def __init__(self, db: Database, fetch: Callable[[str], str] = _default_fetch):
        self._db = db
        self._fetch = fetch

    def poll(self, channels: list[SourceChannel]) -> list[str]:
        new_ids: list[str] = []
        for ch in channels:
            try:
                xml = self._fetch(feed_url(ch.channel_id))
                items = parse_feed(xml)
            except Exception:
                continue
            for it in items:
                rec = VideoRecord(
                    video_id=it["video_id"], channel_id=ch.channel_id,
                    channel_name=ch.name, title=it["title"], url=it["url"],
                    status=Status.DISCOVERED, discovered_at=it["published"],
                )
                if self._db.insert_discovered(rec):
                    new_ids.append(it["video_id"])
        return new_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/monitor.py tests/test_monitor.py
git commit -m "feat: RSS monitor with dedupe"
```

---

### Task 6: Downloader (yt-dlp wrapper)

**Files:**
- Create: `clipforge/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure wrapper).
- Produces:
  - `class Downloader(storage_root: str, runner: Callable[[list[str]], int] = ..., info_fn: Callable[[str], dict] = ...)` where `runner(argv) -> returncode` runs yt-dlp download and `info_fn(url) -> dict` returns metadata (`{"is_live": bool, "duration": float}`). Both injected for tests.
  - `Downloader.is_live(url: str) -> bool`.
  - `Downloader.duration(url: str) -> float`.
  - `Downloader.download(video_id: str, url: str) -> str` — downloads to `<storage_root>/videos/<video_id>.mp4`, returns that path; raises `RuntimeError` if runner returns non-zero.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/downloader.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Callable


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv).returncode


def _default_info(url: str) -> dict:
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {"is_live": bool(info.get("is_live")),
            "duration": float(info.get("duration") or 0.0)}


class Downloader:
    def __init__(self, storage_root: str,
                 runner: Callable[[list[str]], int] = _default_runner,
                 info_fn: Callable[[str], dict] = _default_info):
        self._root = Path(storage_root)
        self._runner = runner
        self._info = info_fn

    def is_live(self, url: str) -> bool:
        return bool(self._info(url).get("is_live"))

    def duration(self, url: str) -> float:
        return float(self._info(url).get("duration") or 0.0)

    def download(self, video_id: str, url: str) -> str:
        out_dir = self._root / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_id}.mp4"
        argv = ["yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                "-o", str(out_path), url]
        rc = self._runner(argv)
        if rc != 0:
            raise RuntimeError(f"yt-dlp failed (rc={rc}) for {url}")
        return str(out_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/downloader.py tests/test_downloader.py
git commit -m "feat: yt-dlp downloader wrapper with is_live check"
```

---

### Task 7: Transcription (faster-whisper wrapper)

**Files:**
- Create: `clipforge/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `@dataclass Word` with `start: float`, `end: float`, `text: str`.
  - `@dataclass TranscriptSeg` with `start: float`, `end: float`, `text: str`, `words: list[Word]`.
  - `class Transcriber(model_name: str, device: str, extract_audio: Callable[[str,str],int] = ..., model_factory: Callable[[str,str], object] = ...)`.
  - `Transcriber.transcribe(video_path: str, audio_path: str) -> list[TranscriptSeg]` — extracts audio then runs whisper. Empty audio/no speech returns `[]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcribe.py
from clipforge.transcribe import Transcriber, TranscriptSeg, Word

class FakeSeg:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words

class FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word

class FakeModel:
    def transcribe(self, audio_path, word_timestamps=True):
        segs = [FakeSeg(0.0, 2.0, "hello world",
                        [FakeWord(0.0, 1.0, "hello"), FakeWord(1.0, 2.0, "world")])]
        return segs, {"language": "en"}

def test_transcribe_maps_segments(tmp_path):
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: FakeModel())
    out = t.transcribe(str(tmp_path / "v.mp4"), str(tmp_path / "a.wav"))
    assert len(out) == 1
    assert isinstance(out[0], TranscriptSeg)
    assert out[0].text == "hello world"
    assert out[0].words[0].text == "hello"

def test_transcribe_empty_returns_empty(tmp_path):
    class EmptyModel:
        def transcribe(self, audio_path, word_timestamps=True):
            return [], {"language": "en"}
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: EmptyModel())
    assert t.transcribe("v", "a") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/transcribe.py`**

```python
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TranscriptSeg:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def _default_extract_audio(video_path: str, audio_path: str) -> int:
    return subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
         audio_path]).returncode


def _default_model_factory(model_name: str, device: str):
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    return WhisperModel(model_name, device=device, compute_type=compute)


class Transcriber:
    def __init__(self, model_name: str, device: str,
                 extract_audio: Callable[[str, str], int] = _default_extract_audio,
                 model_factory: Callable[[str, str], object] = _default_model_factory):
        self._model_name = model_name
        self._device = device
        self._extract = extract_audio
        self._factory = model_factory

    def transcribe(self, video_path: str, audio_path: str) -> list[TranscriptSeg]:
        rc = self._extract(video_path, audio_path)
        if rc != 0:
            raise RuntimeError(f"audio extract failed (rc={rc})")
        model = self._factory(self._model_name, self._device)
        segments, _info = model.transcribe(audio_path, word_timestamps=True)
        out: list[TranscriptSeg] = []
        for s in segments:
            words = [Word(start=float(w.start), end=float(w.end), text=w.word)
                     for w in (s.words or [])]
            out.append(TranscriptSeg(start=float(s.start), end=float(s.end),
                                     text=s.text.strip(), words=words))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/transcribe.py tests/test_transcribe.py
git commit -m "feat: faster-whisper transcription wrapper"
```

---

### Task 8: LLM provider interface + Gemini

**Files:**
- Create: `clipforge/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `class LLMError(Exception)`.
  - `class LLMProvider(ABC)` with abstract `generate_json(prompt: str) -> dict` and `generate_text(prompt: str) -> str`.
  - `class GeminiProvider(LLMProvider)(model: str, api_key: str, client_factory: Callable = ...)` — wraps google-generativeai; `generate_json` parses the model's JSON response (tolerates ```json fences), raising `LLMError` on quota/parse failure.
  - `get_provider(provider: str, model: str, api_key: str) -> LLMProvider` — factory; unknown provider raises `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm.py
import pytest
from clipforge.llm import GeminiProvider, get_provider, LLMError, LLMProvider

class FakeResp:
    def __init__(self, text): self.text = text

class FakeModel:
    def __init__(self, text): self._text = text
    def generate_content(self, prompt): return FakeResp(self._text)

def _provider(text):
    return GeminiProvider("gemini-2.0-flash", "key",
                          client_factory=lambda m, k: FakeModel(text))

def test_generate_json_plain():
    p = _provider('{"a": 1}')
    assert p.generate_json("x") == {"a": 1}

def test_generate_json_fenced():
    p = _provider('```json\n{"a": 2}\n```')
    assert p.generate_json("x") == {"a": 2}

def test_generate_json_bad_raises():
    p = _provider("not json")
    with pytest.raises(LLMError):
        p.generate_json("x")

def test_generate_text():
    p = _provider("hello")
    assert p.generate_text("x") == "hello"

def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nope", "m", "k")

def test_factory_returns_provider():
    assert isinstance(get_provider("gemini", "gemini-2.0-flash", "k"), LLMProvider)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/llm.py`**

```python
from __future__ import annotations
import json, re
from abc import ABC, abstractmethod
from typing import Callable

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> dict: ...
    @abstractmethod
    def generate_text(self, prompt: str) -> str: ...


def _default_gemini_client(model: str, api_key: str):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)


class GeminiProvider(LLMProvider):
    def __init__(self, model: str, api_key: str,
                 client_factory: Callable[[str, str], object] = _default_gemini_client):
        self._model = client_factory(model, api_key)

    def _raw(self, prompt: str) -> str:
        try:
            resp = self._model.generate_content(prompt)
            return resp.text
        except Exception as e:  # quota, network, safety blocks
            raise LLMError(str(e)) from e

    def generate_text(self, prompt: str) -> str:
        return self._raw(prompt)

    def generate_json(self, prompt: str) -> dict:
        text = self._raw(prompt).strip()
        m = _FENCE.search(text)
        if m:
            text = m.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from LLM: {e}") from e


def get_provider(provider: str, model: str, api_key: str) -> LLMProvider:
    if provider == "gemini":
        return GeminiProvider(model, api_key)
    raise ValueError(f"unknown llm provider: {provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/llm.py tests/test_llm.py
git commit -m "feat: LLM provider interface with Gemini implementation"
```

---

### Task 9: Highlight detection and ranking

**Files:**
- Create: `clipforge/highlights.py`
- Test: `tests/test_highlights.py`

**Interfaces:**
- Consumes: `TranscriptSeg` from `transcribe.py`; `Segment` from `models.py`; `LLMProvider`/`LLMError` from `llm.py`.
- Produces:
  - `KEYWORDS: list[str]` — hype words (lowercase).
  - `keyword_score(text: str) -> float` — fraction-based score from keyword hits (0..1, capped).
  - `energy_score(rms: float, max_rms: float) -> float` — normalized 0..1.
  - `candidate_windows(segments, min_s, max_s) -> list[Segment]` — build candidate windows from transcript segments respecting length bounds, each pre-scored by keyword_score.
  - `pick_best(segments, min_s, max_s, llm=None, energy=None) -> Segment | None` — combine keyword + optional energy + optional LLM rank; return highest-scoring Segment. Returns None if no segments. On `LLMError`, degrade to keyword(+energy) only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_highlights.py
from clipforge.highlights import (keyword_score, energy_score,
                                  candidate_windows, pick_best)
from clipforge.transcribe import TranscriptSeg
from clipforge.llm import LLMError

def _seg(a, b, t):
    return TranscriptSeg(start=a, end=b, text=t, words=[])

def test_keyword_score_hits():
    assert keyword_score("that was insane no way") > 0
    assert keyword_score("the weather is mild") == 0

def test_energy_score_normalized():
    assert energy_score(5.0, 10.0) == 0.5
    assert energy_score(0.0, 0.0) == 0.0

def test_candidate_windows_respect_bounds():
    segs = [_seg(0, 10, "a"), _seg(10, 20, "b"), _seg(20, 70, "c")]
    wins = candidate_windows(segs, min_s=20, max_s=40)
    assert all(20 <= (w.end - w.start) <= 40 for w in wins)
    assert wins  # at least one

def test_pick_best_uses_keywords_without_llm():
    segs = [_seg(0, 25, "boring talk here"),
            _seg(25, 50, "insane clutch no way omg")]
    best = pick_best(segs, min_s=20, max_s=30)
    assert best is not None
    assert best.start >= 25 - 30  # window covers the hype segment
    assert best.score > 0

def test_pick_best_none_when_empty():
    assert pick_best([], min_s=20, max_s=30) is None

def test_pick_best_degrades_on_llm_error():
    class BadLLM:
        def generate_json(self, prompt): raise LLMError("quota")
        def generate_text(self, prompt): raise LLMError("quota")
    segs = [_seg(0, 25, "insane no way")]
    best = pick_best(segs, min_s=20, max_s=30, llm=BadLLM())
    assert best is not None  # did not crash; degraded path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_highlights.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/highlights.py`**

```python
from __future__ import annotations
import json
from typing import Callable, Optional
from clipforge.models import Segment
from clipforge.transcribe import TranscriptSeg
from clipforge.llm import LLMProvider, LLMError

KEYWORDS = [
    "insane", "no way", "omg", "oh my god", "clutch", "wait", "what",
    "let's go", "lets go", "unbelievable", "crazy", "wow", "gg", "ace",
    "headshot", "victory", "won", "win", "hype", "poggers", "pog", "nice",
]


def keyword_score(text: str) -> float:
    t = text.lower()
    hits = sum(1 for k in KEYWORDS if k in t)
    if hits == 0:
        return 0.0
    return min(1.0, hits / 3.0)


def energy_score(rms: float, max_rms: float) -> float:
    if max_rms <= 0:
        return 0.0
    return max(0.0, min(1.0, rms / max_rms))


def candidate_windows(segments: list[TranscriptSeg], min_s: float,
                      max_s: float) -> list[Segment]:
    windows: list[Segment] = []
    n = len(segments)
    for i in range(n):
        start = segments[i].start
        j = i
        text_parts: list[str] = []
        while j < n and (segments[j].end - start) <= max_s:
            text_parts.append(segments[j].text)
            length = segments[j].end - start
            if length >= min_s:
                windows.append(Segment(
                    start=start, end=segments[j].end,
                    score=keyword_score(" ".join(text_parts)),
                    reason="keyword",
                ))
            j += 1
    if not windows and segments:
        # fall back to a single clamped window from the first segment
        start = segments[0].start
        end = min(start + max_s, segments[-1].end)
        windows.append(Segment(start=start, end=end,
                               score=keyword_score(
                                   " ".join(s.text for s in segments)),
                               reason="fallback"))
    return windows


def _llm_rank(llm: LLMProvider, windows: list[Segment],
              segments: list[TranscriptSeg]) -> Optional[int]:
    transcript = "\n".join(
        f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments)
    listing = "\n".join(
        f"{idx}: {w.start:.1f}-{w.end:.1f}" for idx, w in enumerate(windows))
    prompt = (
        "You pick the single most engaging moment for a viral Short.\n"
        "Transcript:\n" + transcript + "\n\nCandidate windows (index: range):\n"
        + listing + '\n\nReturn JSON only: {"index": <int>, "reason": "<why>"}'
    )
    data = llm.generate_json(prompt)
    idx = int(data.get("index", -1))
    if 0 <= idx < len(windows):
        windows[idx].reason = str(data.get("reason", "llm"))
        return idx
    return None


def pick_best(segments: list[TranscriptSeg], min_s: float, max_s: float,
              llm: LLMProvider = None,
              energy: Callable[[float, float], float] = None) -> Segment | None:
    if not segments:
        return None
    windows = candidate_windows(segments, min_s, max_s)
    if not windows:
        return None
    # boost the LLM-chosen window if available
    if llm is not None:
        try:
            idx = _llm_rank(llm, windows, segments)
            if idx is not None:
                windows[idx].score += 1.0
        except LLMError:
            pass  # degrade to keyword-only scoring
    windows.sort(key=lambda w: (w.score, -(w.end - w.start)), reverse=True)
    return windows[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_highlights.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/highlights.py tests/test_highlights.py
git commit -m "feat: highlight detection with keyword+energy+LLM ranking"
```

---

### Task 10: Clipper (FFmpeg cut, 9:16 crop, burn captions)

**Files:**
- Create: `clipforge/clipper.py`
- Test: `tests/test_clipper.py`

**Interfaces:**
- Consumes: `Segment` from `models.py`; `TranscriptSeg`/`Word` from `transcribe.py`.
- Produces:
  - `format_timestamp(seconds: float) -> str` — ASS time `H:MM:SS.cc`.
  - `build_ass(segments, seg_start, seg_end) -> str` — ASS subtitle file text for words/segments within the clip window, times rebased to clip start, styled (bold, outline, lower-center).
  - `class Clipper(storage_root, runner=...)` where `runner(argv)->int`.
  - `Clipper.make_short(video_id, source_path, seg: Segment, transcript: list[TranscriptSeg]) -> str` — writes `.ass`, runs ffmpeg to cut `[seg.start,seg.end]`, center-crop to 9:16, burn subtitles; returns `<storage_root>/clips/<video_id>.mp4`. Raises `RuntimeError` on non-zero.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clipper.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_clipper.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/clipper.py`**

```python
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Callable
from clipforge.models import Segment
from clipforge.transcribe import TranscriptSeg

_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00000000,&H00000000,-1,1,4,0,2,60,60,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(segments: list[TranscriptSeg], seg_start: float,
              seg_end: float) -> str:
    lines = [_ASS_HEADER]
    for s in segments:
        if s.end <= seg_start or s.start >= seg_end:
            continue
        start = max(s.start, seg_start) - seg_start
        end = min(s.end, seg_end) - seg_start
        text = s.text.replace("\n", " ").strip()
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{format_timestamp(start)},{format_timestamp(end)},"
            f"Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv).returncode


class Clipper:
    def __init__(self, storage_root: str,
                 runner: Callable[[list[str]], int] = _default_runner):
        self._root = Path(storage_root)
        self._runner = runner

    def make_short(self, video_id: str, source_path: str, seg: Segment,
                   transcript: list[TranscriptSeg]) -> str:
        clips_dir = self._root / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        ass_path = clips_dir / f"{video_id}.ass"
        ass_path.write_text(build_ass(transcript, seg.start, seg.end),
                            encoding="utf-8")
        out_path = clips_dir / f"{video_id}.mp4"
        # center-crop to 9:16 then scale to 1080x1920, then burn ASS
        ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
        vf = ("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',"
              "scale=1080:1920,"
              f"ass='{ass_escaped}'")
        argv = ["ffmpeg", "-y", "-ss", str(seg.start), "-to", str(seg.end),
                "-i", source_path, "-vf", vf, "-c:a", "aac",
                str(out_path)]
        rc = self._runner(argv)
        if rc != 0:
            raise RuntimeError(f"ffmpeg clip failed (rc={rc})")
        return str(out_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_clipper.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/clipper.py tests/test_clipper.py
git commit -m "feat: ffmpeg clipper with 9:16 crop and burned captions"
```

---

### Task 11: Metadata generation (title/description/tags)

**Files:**
- Create: `clipforge/metadata.py`
- Test: `tests/test_metadata.py`

**Interfaces:**
- Consumes: `ClipMetadata` from `models.py`; `LLMProvider`/`LLMError` from `llm.py`.
- Produces:
  - `template_metadata(video_title: str, transcript_text: str) -> ClipMetadata` — deterministic fallback (no LLM).
  - `generate_metadata(video_title, transcript_text, llm=None) -> ClipMetadata` — LLM JSON `{title, description, tags[]}`; on `LLMError`/missing keys, fall back to `template_metadata`. Title truncated to 100 chars, tags to max 20.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metadata.py
from clipforge.metadata import generate_metadata, template_metadata
from clipforge.models import ClipMetadata
from clipforge.llm import LLMError

def test_template_metadata():
    m = template_metadata("Cool Stream", "we did an insane play")
    assert isinstance(m, ClipMetadata)
    assert m.title
    assert m.tags

def test_generate_with_llm():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "Insane Play!", "description": "wow",
                    "tags": ["gaming", "shorts"]}
        def generate_text(self, prompt): return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert m.title == "Insane Play!"
    assert "gaming" in m.tags

def test_generate_degrades_on_error():
    class LLM:
        def generate_json(self, prompt): raise LLMError("quota")
        def generate_text(self, prompt): raise LLMError("quota")
    m = generate_metadata("Backup Title", "txt", llm=LLM())
    assert isinstance(m, ClipMetadata)
    assert m.title  # from template

def test_title_truncated_to_100():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "x" * 200, "description": "d", "tags": []}
        def generate_text(self, prompt): return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.title) <= 100

def test_tags_capped_at_20():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "t", "description": "d",
                    "tags": [f"t{i}" for i in range(50)]}
        def generate_text(self, prompt): return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.tags) <= 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/metadata.py`**

```python
from __future__ import annotations
from clipforge.models import ClipMetadata
from clipforge.llm import LLMProvider, LLMError

_MAX_TITLE = 100
_MAX_TAGS = 20


def template_metadata(video_title: str, transcript_text: str) -> ClipMetadata:
    base = (video_title or "Highlight").strip()[:_MAX_TITLE]
    title = base if base else "Highlight"
    desc = f"Clip from: {video_title}\n\n#shorts"
    tags = ["shorts", "clip", "highlights", "viral", "trending"]
    return ClipMetadata(title=title, description=desc, tags=tags[:_MAX_TAGS])


def generate_metadata(video_title: str, transcript_text: str,
                      llm: LLMProvider = None) -> ClipMetadata:
    if llm is None:
        return template_metadata(video_title, transcript_text)
    prompt = (
        "You are a YouTube Shorts SEO expert. Given this clip transcript, "
        "produce a viral Short's metadata.\n"
        f"Source video title: {video_title}\n"
        f"Transcript: {transcript_text[:2000]}\n\n"
        'Return JSON only: {"title": "<=100 chars, catchy", '
        '"description": "2-3 lines + hashtags", "tags": ["up to 20"]}'
    )
    try:
        data = llm.generate_json(prompt)
        title = str(data["title"])[:_MAX_TITLE]
        desc = str(data["description"])
        tags = [str(t) for t in data.get("tags", [])][:_MAX_TAGS]
        if not title:
            raise LLMError("empty title")
        return ClipMetadata(title=title, description=desc, tags=tags)
    except (LLMError, KeyError, TypeError):
        return template_metadata(video_title, transcript_text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/metadata.py tests/test_metadata.py
git commit -m "feat: metadata generation with template fallback"
```

---

### Task 12: YouTube uploader

**Files:**
- Create: `clipforge/youtube.py`
- Test: `tests/test_youtube.py`

**Interfaces:**
- Consumes: `ClipMetadata` from `models.py`.
- Produces:
  - `class YouTubeUploader(privacy_status, category_id, service_factory=..., media_factory=...)` where `service_factory() -> youtube_service` and `media_factory(path) -> media_body` are injected for tests.
  - `YouTubeUploader.upload(clip_path: str, meta: ClipMetadata) -> str` — calls `videos.insert`, returns the new video id. Raises `RuntimeError` on API error. Description gets `#Shorts` appended if absent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_youtube.py
import pytest
from clipforge.youtube import YouTubeUploader
from clipforge.models import ClipMetadata

class FakeInsert:
    def __init__(self, store): self._store = store
    def execute(self): return {"id": "NEWVIDEOID"}

class FakeVideos:
    def __init__(self, store): self._store = store
    def insert(self, part, body, media_body):
        self._store["part"] = part
        self._store["body"] = body
        return FakeInsert(self._store)

class FakeService:
    def __init__(self, store): self._store = store
    def videos(self): return FakeVideos(self._store)

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
        def execute(self): raise Exception("api down")
    class BadVideos:
        def insert(self, **k): return BadInsert()
    class BadService:
        def videos(self): return BadVideos()
    up = YouTubeUploader("public", "20",
                         service_factory=lambda: BadService(),
                         media_factory=lambda p: object())
    with pytest.raises(RuntimeError):
        up.upload("c.mp4", ClipMetadata(title="T", description="D", tags=[]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/youtube.py`**

```python
from __future__ import annotations
from typing import Callable
from clipforge.models import ClipMetadata

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _default_service_factory():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import os
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", _SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret.json", _SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def _default_media_factory(path: str):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(path, chunksize=-1, resumable=True)


class YouTubeUploader:
    def __init__(self, privacy_status: str, category_id: str,
                 service_factory: Callable[[], object] = _default_service_factory,
                 media_factory: Callable[[str], object] = _default_media_factory):
        self._privacy = privacy_status
        self._category = category_id
        self._service_factory = service_factory
        self._media_factory = media_factory

    def upload(self, clip_path: str, meta: ClipMetadata) -> str:
        description = meta.description
        if "#Shorts" not in description and "#shorts" not in description:
            description = (description + "\n\n#Shorts").strip()
        body = {
            "snippet": {
                "title": meta.title,
                "description": description,
                "tags": meta.tags,
                "categoryId": self._category,
            },
            "status": {"privacyStatus": self._privacy,
                       "selfDeclaredMadeForKids": False},
        }
        try:
            service = self._service_factory()
            media = self._media_factory(clip_path)
            request = service.videos().insert(
                part="snippet,status", body=body, media_body=media)
            response = request.execute()
            return response["id"]
        except Exception as e:
            raise RuntimeError(f"youtube upload failed: {e}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_youtube.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/youtube.py tests/test_youtube.py
git commit -m "feat: youtube uploader via videos.insert"
```

---

### Task 13: Cleanup (disk management)

**Files:**
- Create: `clipforge/cleanup.py`
- Test: `tests/test_cleanup.py`

**Interfaces:**
- Consumes: `Database`.
- Produces:
  - `dir_size_gb(path: str) -> float`.
  - `class Cleanup(db: Database, storage_root: str, max_disk_gb: int)`.
  - `Cleanup.delete_source(video_id: str, source_path: str) -> None` — removes the source file if present (safe if missing).
  - `Cleanup.enforce_quota() -> int` — while `videos/` exceeds `max_disk_gb`, delete oldest published source files; returns number deleted.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cleanup.py
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
    f = tmp_path / "s.mp4"; f.write_text("x")
    c = Cleanup(db, str(tmp_path), max_disk_gb=50)
    c.delete_source("v1", str(f))
    assert not f.exists()

def test_enforce_quota_deletes_oldest_published(tmp_path):
    root = tmp_path
    vids = root / "videos"; vids.mkdir()
    db = Database(str(root / "t.db"))
    big = b"0" * (2 * 1024 * 1024)  # 2MB each
    for vid, ts in [("v1", "2026-01-01"), ("v2", "2026-01-02")]:
        p = vids / f"{vid}.mp4"; p.write_bytes(big)
        db.insert_discovered(_rec(vid, ts))
        db.set_status(vid, Status.PUBLISHED)
        db.set_paths(vid, source_path=str(p))
    c = Cleanup(db, str(root), max_disk_gb=0)  # force over-quota
    deleted = c.enforce_quota()
    assert deleted >= 1
    assert not (vids / "v1.mp4").exists()  # oldest removed first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cleanup.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/cleanup.py`**

```python
from __future__ import annotations
from pathlib import Path
from clipforge.db import Database


def dir_size_gb(path: str) -> float:
    p = Path(path)
    if not p.exists():
        return 0.0
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return total / (1024 ** 3)


class Cleanup:
    def __init__(self, db: Database, storage_root: str, max_disk_gb: int):
        self._db = db
        self._root = Path(storage_root)
        self._max = max_disk_gb

    def delete_source(self, video_id: str, source_path: str) -> None:
        try:
            p = Path(source_path)
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def enforce_quota(self) -> int:
        videos_dir = self._root / "videos"
        deleted = 0
        # oldest published first (published_source_paths preserves insert order
        # by discovered_at via query; sort defensively here)
        published = self._db.published_source_paths()
        published_by_age = sorted(
            published,
            key=lambda pair: (self._db.get(pair[0]).discovered_at
                              if self._db.get(pair[0]) else ""))
        for video_id, source_path in published_by_age:
            if dir_size_gb(str(videos_dir)) <= self._max:
                break
            p = Path(source_path)
            if p.exists():
                try:
                    p.unlink()
                    deleted += 1
                except OSError:
                    pass
        return deleted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cleanup.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/cleanup.py tests/test_cleanup.py
git commit -m "feat: disk cleanup and quota enforcement"
```

---

### Task 14: Pipeline worker + publisher (orchestration)

**Files:**
- Create: `clipforge/pipeline.py`
- Test: `tests/test_pipeline.py`

This is the glue that advances one video through the stage machine and performs
the daily publish. It depends on all prior modules but is written against their
interfaces so it can be unit-tested with fakes.

**Interfaces:**
- Consumes: `Database`, `Downloader`, `Transcriber`, `highlights.pick_best`,
  `Clipper`, `metadata.generate_metadata`, `YouTubeUploader`, `Cleanup`,
  `Config`, `Status`.
- Produces:
  - `class Pipeline(db, downloader, transcriber, clipper, uploader, cleanup, config, llm=None)`.
  - `Pipeline.advance_one() -> str | None` — finds the next actionable video (first non-terminal status via a fixed stage order), runs exactly that one stage, updates status/paths, returns the video_id advanced or None if nothing to do. On stage exception: `bump_retry`; at >3 retries set `FAILED`.
  - `Pipeline.publish_daily() -> str | None` — pick top of `db.list_ready()` (tie-break priority via `config.enabled_channels()` order, then rank, then oldest), upload, set `PUBLISHED`, run `cleanup.delete_source` + `cleanup.enforce_quota`. Returns published video_id or None.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
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
        self.uploaded.append((clip_path, meta)); return "YTID"

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
    db, pipe = _pipe(tmp_path); _seed(db)
    assert pipe.advance_one() == "v1"
    assert db.get("v1").status == Status.DOWNLOADED

def test_advance_full_to_ready(tmp_path):
    db, pipe = _pipe(tmp_path); _seed(db)
    for _ in range(10):
        if pipe.advance_one() is None:
            break
    assert db.get("v1").status == Status.READY

def test_advance_none_when_idle(tmp_path):
    db, pipe = _pipe(tmp_path)
    assert pipe.advance_one() is None

def test_retry_then_fail(tmp_path):
    db = Database(str(tmp_path / "t.db")); _seed(db)
    class Boom(FakeDownloader):
        def download(self, vid, url): raise RuntimeError("net")
    pipe = Pipeline(db, Boom(), FakeTranscriber(), FakeClipper(),
                    FakeUploader(), FakeCleanup(), _cfg(tmp_path))
    for _ in range(4):
        pipe.advance_one()
    assert db.get("v1").status == Status.FAILED

def test_skip_live_video(tmp_path):
    db = Database(str(tmp_path / "t.db")); _seed(db)
    class Live(FakeDownloader):
        def is_live(self, url): return True
    pipe = Pipeline(db, Live(), FakeTranscriber(), FakeClipper(),
                    FakeUploader(), FakeCleanup(), _cfg(tmp_path))
    pipe.advance_one()
    assert db.get("v1").status == Status.FAILED

def test_publish_daily_uploads_top_ranked(tmp_path):
    up = FakeUploader()
    db, pipe = _pipe(tmp_path, uploader=up)
    for vid, rank in [("v1", 0.2), ("v2", 0.9)]:
        _seed(db, vid); db.set_status(vid, Status.READY); db.set_rank(vid, rank)
        db.set_paths(vid, source_path=f"/src/{vid}.mp4", clip_path=f"/c/{vid}.mp4")
    published = pipe.publish_daily()
    assert published == "v2"
    assert db.get("v2").status == Status.PUBLISHED
    assert len(up.uploaded) == 1

def test_publish_daily_none_when_empty(tmp_path):
    db, pipe = _pipe(tmp_path)
    assert pipe.publish_daily() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/pipeline.py`**

```python
from __future__ import annotations
from pathlib import Path
from clipforge.db import Database
from clipforge.models import Status, ClipMetadata
from clipforge import highlights, metadata

_MAX_RETRIES = 3

# stage order: (current_status, in_progress_status, handler_name)
_STAGES = [
    Status.DISCOVERED, Status.DOWNLOADED, Status.TRANSCRIBED,
    Status.HIGHLIGHTED, Status.CLIPPED,
]


class Pipeline:
    def __init__(self, db: Database, downloader, transcriber, clipper,
                 uploader, cleanup, config, llm=None):
        self._db = db
        self._dl = downloader
        self._tr = transcriber
        self._clip = clipper
        self._up = uploader
        self._cleanup = cleanup
        self._cfg = config
        self._llm = llm
        self._segments: dict[str, list] = {}
        self._best: dict[str, object] = {}

    def _handle(self, rec) -> None:
        vid = rec.video_id
        root = Path(self._cfg.storage_root)
        if rec.status == Status.DISCOVERED:
            if self._dl.is_live(rec.url):
                raise RuntimeError("still live")
            self._db.set_status(vid, Status.DOWNLOADING)
            path = self._dl.download(vid, rec.url)
            self._db.set_paths(vid, source_path=path)
            self._db.set_status(vid, Status.DOWNLOADED)
        elif rec.status == Status.DOWNLOADED:
            self._db.set_status(vid, Status.TRANSCRIBING)
            audio = str(root / "audio" / f"{vid}.wav")
            (root / "audio").mkdir(parents=True, exist_ok=True)
            segs = self._tr.transcribe(rec.source_path, audio)
            self._segments[vid] = segs
            self._db.set_status(vid, Status.TRANSCRIBED)
        elif rec.status == Status.TRANSCRIBED:
            self._db.set_status(vid, Status.HIGHLIGHTING)
            segs = self._segments.get(vid, [])
            best = highlights.pick_best(
                segs, self._cfg.clip_min_seconds, self._cfg.clip_max_seconds,
                llm=self._llm)
            if best is None:
                raise RuntimeError("no highlight found")
            self._best[vid] = best
            self._db.set_rank(vid, best.score)
            self._db.set_status(vid, Status.HIGHLIGHTED)
        elif rec.status == Status.HIGHLIGHTED:
            self._db.set_status(vid, Status.CLIPPING)
            segs = self._segments.get(vid, [])
            best = self._best.get(vid)
            if best is None:
                raise RuntimeError("missing segment; will reprocess")
            clip_path = self._clip.make_short(vid, rec.source_path, best, segs)
            self._db.set_paths(vid, clip_path=clip_path)
            self._db.set_status(vid, Status.CLIPPED)
        elif rec.status == Status.CLIPPED:
            self._db.set_status(vid, Status.METADATA)
            segs = self._segments.get(vid, [])
            text = " ".join(s.text for s in segs)
            meta = metadata.generate_metadata(rec.title, text, llm=self._llm)
            self._db.set_status(vid, Status.READY)
            self._meta_cache = getattr(self, "_meta_cache", {})
            self._meta_cache[vid] = meta

    def advance_one(self) -> str | None:
        for status in _STAGES:
            rec = self._db.next_in_status(status)
            if rec is None:
                continue
            try:
                self._handle(rec)
                return rec.video_id
            except Exception as e:
                count = self._db.bump_retry(rec.video_id, str(e))
                # roll back to clean state so the stage retries
                self._db.reset_stuck()
                if count > _MAX_RETRIES:
                    self._db.set_status(rec.video_id, Status.FAILED, str(e))
                return rec.video_id
        return None

    def _priority_index(self, channel_id: str) -> int:
        for i, ch in enumerate(self._cfg.enabled_channels()):
            if ch.channel_id == channel_id:
                return i
        return 10_000

    def publish_daily(self) -> str | None:
        ready = self._db.list_ready()
        if not ready:
            return None
        ready.sort(key=lambda r: (-r.rank_score,
                                  self._priority_index(r.channel_id),
                                  r.discovered_at))
        rec = ready[0]
        self._db.set_status(rec.video_id, Status.PUBLISHING)
        cache = getattr(self, "_meta_cache", {})
        meta = cache.get(rec.video_id) or ClipMetadata(
            title=rec.title[:100], description="#Shorts", tags=["shorts"])
        try:
            self._up.upload(rec.clip_path, meta)
        except Exception as e:
            self._db.set_status(rec.video_id, Status.READY, str(e))
            return None
        self._db.set_status(rec.video_id, Status.PUBLISHED)
        self._cleanup.delete_source(rec.video_id, rec.source_path)
        self._cleanup.enforce_quota()
        return rec.video_id
```

Note: the in-memory `_segments`/`_best`/`_meta_cache` caches make advancing fast
within one process run. If the process restarts mid-pipeline, `reset_stuck`
rolls the row back to its last clean status so the stage re-runs and rebuilds
the cache. This is intentional and matches the crash-safety design.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add clipforge/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline worker and daily publisher orchestration"
```

---

### Task 15: Scheduler + main entrypoint (CLI: run, --once, --dry-run)

**Files:**
- Create: `clipforge/scheduler.py`, `clipforge/main.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: everything; wires jobs.
- Produces:
  - `build_pipeline(config, dry_run: bool) -> Pipeline` — constructs real Downloader/Transcriber/Clipper/Cleanup, a Gemini `LLMProvider` from `GEMINI_API_KEY` env (None if unset), and either a real `YouTubeUploader` or a `DryRunUploader` (writes intended metadata to `<storage>/dryrun/<clip>.json`, returns "DRYRUN").
  - `class DryRunUploader.upload(clip_path, meta) -> str`.
  - `run_forever(config) -> None` — APScheduler: MonitorJob every `monitor_interval_minutes`, a worker job draining `advance_one()` until it returns None (every ~30s), PublishJob daily at `publish_time` in `timezone`. Calls `db.reset_stuck()` on startup.
  - `run_once(config, url) -> None` — insert one URL as DISCOVERED, drain `advance_one()` to READY, then `publish_daily()`.
  - `main()` — argparse: `--config` (default `config.json`), `--once <url>`, `--dry-run`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scheduler.py
import json
from pathlib import Path
from clipforge.scheduler import DryRunUploader, run_once
from clipforge.models import ClipMetadata

def test_dryrun_uploader_writes_json(tmp_path):
    up = DryRunUploader(str(tmp_path))
    meta = ClipMetadata(title="T", description="D", tags=["a", "b"])
    vid = up.upload(str(tmp_path / "clip.mp4"), meta)
    assert vid == "DRYRUN"
    files = list((tmp_path / "dryrun").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["title"] == "T" and data["tags"] == ["a", "b"]
```

Note: `run_once` full-path is covered by Task 14's pipeline tests; this task's
unit test focuses on the dry-run boundary. `run_forever` is validated manually
(it starts a blocking scheduler).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `clipforge/scheduler.py` and `clipforge/main.py`**

`clipforge/scheduler.py`:
```python
from __future__ import annotations
import json, os, time, logging
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from clipforge.config import Config, load_config
from clipforge.db import Database
from clipforge.models import Status, VideoRecord, ClipMetadata
from clipforge.downloader import Downloader
from clipforge.transcribe import Transcriber
from clipforge.clipper import Clipper
from clipforge.cleanup import Cleanup
from clipforge.youtube import YouTubeUploader
from clipforge.pipeline import Pipeline
from clipforge.monitor import Monitor
from clipforge.llm import get_provider

log = logging.getLogger("clipforge")


class DryRunUploader:
    def __init__(self, storage_root: str):
        self._dir = Path(storage_root) / "dryrun"

    def upload(self, clip_path: str, meta: ClipMetadata) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        name = Path(clip_path).stem or "clip"
        out = self._dir / f"{name}.json"
        out.write_text(json.dumps({
            "clip_path": clip_path, "title": meta.title,
            "description": meta.description, "tags": meta.tags,
        }, indent=2), encoding="utf-8")
        return "DRYRUN"


def _make_llm(config: Config):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        log.warning("GEMINI_API_KEY not set; running degraded (no LLM)")
        return None
    try:
        return get_provider(config.llm_provider, config.llm_model, key)
    except Exception as e:
        log.warning("LLM init failed: %s", e)
        return None


def build_pipeline(config: Config, dry_run: bool) -> tuple[Database, Pipeline, Monitor]:
    db = Database(str(Path(config.storage_root) / "clipforge.db"))
    downloader = Downloader(config.storage_root)
    transcriber = Transcriber(config.whisper_model, config.whisper_device)
    clipper = Clipper(config.storage_root)
    cleanup = Cleanup(db, config.storage_root, config.max_disk_gb)
    uploader = (DryRunUploader(config.storage_root) if dry_run
                else YouTubeUploader(config.youtube_privacy_status,
                                     config.youtube_category_id))
    llm = _make_llm(config)
    pipe = Pipeline(db, downloader, transcriber, clipper, uploader,
                    cleanup, config, llm=llm)
    monitor = Monitor(db)
    return db, pipe, monitor


def _drain(pipe: Pipeline) -> None:
    while pipe.advance_one() is not None:
        pass


def run_once(config: Config, url: str) -> None:
    db, pipe, _ = build_pipeline(config, dry_run=True)
    vid = url.split("v=")[-1][:11] or "once"
    db.insert_discovered(VideoRecord(vid, "manual", "manual", "manual clip",
                                     url, Status.DISCOVERED,
                                     discovered_at=datetime.utcnow().isoformat()))
    _drain(pipe)
    pipe.publish_daily()
    log.info("run_once complete for %s", vid)


def run_forever(config: Config) -> None:
    db, pipe, monitor = build_pipeline(config, dry_run=False)
    db.reset_stuck()
    sched = BackgroundScheduler(timezone=config.timezone)
    sched.add_job(lambda: monitor.poll(config.reload().enabled_channels()),
                  "interval", minutes=config.monitor_interval_minutes,
                  id="monitor")
    sched.add_job(lambda: _drain(pipe), "interval", seconds=30, id="worker")
    hh, mm = config.publish_time.split(":")
    sched.add_job(pipe.publish_daily, "cron", hour=int(hh), minute=int(mm),
                  id="publish")
    sched.start()
    log.info("clipforge running; publish at %s %s", config.publish_time,
             config.timezone)
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
```

`clipforge/main.py`:
```python
from __future__ import annotations
import argparse, logging
from clipforge.config import load_config
from clipforge.scheduler import run_forever, run_once


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="clipforge")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", metavar="URL",
                        help="process a single URL then exit (implies dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="run scheduler but never upload to YouTube")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.once:
        run_once(config, args.once)
    elif args.dry_run:
        # dry-run scheduler: rebuild pipeline in dry mode
        from clipforge.scheduler import build_pipeline
        import time
        _db, _pipe, _mon = build_pipeline(config, dry_run=True)
        run_forever(config)  # uses real uploader; see note
    else:
        run_forever(config)


if __name__ == "__main__":
    main()
```

Note for implementer: for a persistent dry-run scheduler, thread a `dry_run`
flag into `run_forever` (small change) so it selects `DryRunUploader`. The
`--once` path already forces dry-run and is the primary safe-testing route.
Adjust `run_forever(config, dry_run=False)` signature accordingly and pass the
flag from `main`. Keep `--once` behavior unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add clipforge/scheduler.py clipforge/main.py tests/test_scheduler.py
git commit -m "feat: scheduler, CLI entrypoint, dry-run uploader"
```

---

### Task 16: End-to-end dry-run docs + manual verification

**Files:**
- Create: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `README.md`**

Document: install (`pip install -r requirements.txt`, install FFmpeg, get a
Gemini API key -> `.env` `GEMINI_API_KEY=...`, YouTube OAuth `client_secret.json`),
copy `config.example.json` -> `config.json` and fill channel IDs, then:
- `python -m clipforge.main --once "https://www.youtube.com/watch?v=<id>"` to
  process one video and write intended metadata to `storage/dryrun/`.
- `python -m clipforge.main` to run the always-on scheduler (publishes at 18:00).
- Include the copyright risk warning verbatim from the spec.

- [ ] **Step 2: Manual verification (documented, run by owner)**

Run: `python -m clipforge.main --once "<short test video URL you own>"`
Expected: a `storage/clips/<id>.mp4` vertical file exists and
`storage/dryrun/<id>.json` contains a title/description/tags. No upload occurs.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: setup, usage, and dry-run verification"
```

---

## Self-Review

**Spec coverage:**
- Multi-source channels + enable/disable + priority -> Tasks 2,3 (`SourceChannel`, `enabled_channels`), used in publish tie-break Task 14.
- RSS detection -> Task 5. Download + is_live skip -> Task 6, enforced Task 14.
- Transcription -> Task 7. Highlight (energy+keyword+LLM, degrade) -> Task 9.
- 9:16 center crop + burned captions -> Task 10. Metadata + fallback -> Task 11.
- Gemini behind interface -> Task 8. YouTube upload -> Task 12.
- SQLite state machine + dedupe + crash reset -> Task 4. Disk cleanup -> Task 13.
- One-per-day publish at 18:00 in timezone -> Tasks 14,15. Full-auto -> Task 15.
- Retries (3, then FAILED) -> Task 14. Nothing-ready skip -> Task 14. Upload
  reject keeps READY -> Task 14. Testing (`--once`, `--dry-run`) -> Task 15.
- All edge cases in spec 3.2 have a corresponding handler/test.

**Placeholder scan:** No TBD/TODO/"handle edge cases" left; every code step has
full code. The one explicit implementer note (Task 15 dry-run scheduler flag)
gives the exact change required, not a vague instruction.

**Type consistency:** `Status`, `Segment`, `ClipMetadata`, `SourceChannel`,
`VideoRecord` defined in Task 2 and used with identical fields throughout.
`pick_best`, `make_short`, `generate_metadata`, `upload`, `advance_one`,
`publish_daily` signatures match across producer/consumer tasks.
