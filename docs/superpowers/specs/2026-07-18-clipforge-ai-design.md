# ClipForge AI — v1 Design Spec

- **Date:** 2026-07-18
- **Status:** Approved (design), pending implementation plan
- **Owner:** Project owner (runs on personal Windows PC)

---

## 1. Overview & Scope

ClipForge AI is a Python automation that runs continuously on an always-on
Windows PC. It watches a configurable list of YouTube source channels. When a
new video (or finished livestream VOD) appears, it downloads it, transcribes it,
finds the single best moment, produces a vertical 9:16 Short with burned-in
captions and AI-generated title/description/tags, and adds it to a "ready"
queue. Every day at **18:00 local time**, it publishes exactly **one** Short
from that queue to the owner's YouTube channel. SQLite tracks all state so
nothing is processed or posted twice.

No web dashboard in v1. Configuration is via a JSON file; observability is via
logs and the SQLite database.

### In scope (v1)

- Multiple **source** channels, individually enable/disable + priority.
- Continuous monitoring via RSS.
- Automatic download (yt-dlp).
- Transcription (faster-whisper).
- Highlight detection: audio energy + transcript keywords + LLM ranking.
- Single best clip per source video.
- Center-crop to 9:16.
- Burned-in styled subtitles (1–2 line blocks).
- AI-generated title / description / tags (Gemini free tier).
- Daily publish of exactly one Short at 18:00 local time.
- Full-auto upload (no human approval step).
- SQLite state, dedupe, crash-safe resume.
- Auto disk cleanup after publish.

### Out of scope (deferred to later phases)

- Next.js / FastAPI web dashboard.
- YOLO / game-specific event detection (kills, scoreboards).
- Face-tracking crop.
- Animated word-by-word ("karaoke") captions.
- Analytics-driven learning loop.
- Thumbnail generation.
- Publishing more than one Short per day.
- Multiple destination channels.
- Local Ollama LLM (interface allows it later; not built in v1).

### Risk acknowledgment (on the record)

This tool downloads and re-uploads content from channels the owner does **not**
own and has **no permission** from. This carries a real, high risk of:

- Content ID claims (revenue redirected to the original creator),
- copyright strikes (three strikes terminates the channel),
- permanent channel termination for reused/spam content.

The owner has explicitly chosen **full-auto upload accepting this risk**. This
spec documents the risk; the tool will implement full-auto upload as requested.

---

## 2. Architecture & Configuration

### 2.1 Runtime model

A single long-running Python process (`clipforge`), started once and left
running. Internally it uses APScheduler with three recurring jobs plus a worker,
all coordinated through SQLite:

```
┌─────────────────────────────────────────────────────────┐
│                  clipforge (one process)                 │
│  APScheduler                                             │
│   ├── MonitorJob    every 10 min  → find new videos      │
│   ├── ProcessWorker continuous    → build Shorts         │
│   └── PublishJob    daily 18:00   → publish 1 Short      │
│         all coordinated through SQLite (state)           │
└─────────────────────────────────────────────────────────┘
```

Rationale: on a single PC, one supervised process is simpler to run, debug, and
recover than a multi-service SaaS. Can be split later if moved to a server.

### 2.2 Pipeline / data flow

```
MonitorJob (every 10 min)
  For each ENABLED source channel:
    read RSS feed → new video_id not in DB?
       → insert row: status = DISCOVERED

ProcessWorker (picks up DISCOVERED rows, one at a time)
  DISCOVERED → download (yt-dlp)                  → DOWNLOADED
  DOWNLOADED → extract audio + Whisper transcript → TRANSCRIBED
  TRANSCRIBED→ highlight detect (energy + keywords
               + LLM rank) → pick best segment    → HIGHLIGHTED
  HIGHLIGHTED→ cut clip, center-crop 9:16,
               burn captions (FFmpeg)             → CLIPPED
  CLIPPED    → Gemini: title/description/tags     → READY

PublishJob (daily 18:00 local)
  pick 1 READY clip (ranked, tie-break by channel
  priority) → YouTube upload → PUBLISHED
  (nothing READY? log and skip)
```

Each stage is an isolated module reading/writing status in SQLite. On restart,
the worker resumes from each video's last committed clean state.

### 2.3 Component modules

| Module | Responsibility |
|---|---|
| `config.py` | Load & validate `config.json`; hot-reload channel list |
| `db.py` | SQLite schema + all state transitions |
| `monitor.py` | RSS polling, new-video detection |
| `downloader.py` | yt-dlp download + catalog |
| `transcribe.py` | audio extract + faster-whisper |
| `highlights.py` | audio energy + keyword + LLM ranking → best segment |
| `clipper.py` | FFmpeg cut, center-crop 9:16, burn captions |
| `metadata.py` | LLM → title/description/tags |
| `youtube.py` | OAuth + `videos.insert` upload |
| `llm.py` | LLM provider interface (Gemini impl; Ollama later) |
| `scheduler.py` | wires the 3 jobs + worker |
| `main.py` | entrypoint, logging, graceful shutdown, CLI flags |

### 2.4 Configuration (`config.json`)

```jsonc
{
  "source_channels": [
    { "name": "Tarik", "channel_id": "UC...", "enabled": true, "priority": 1 }
  ],
  "publish_time": "18:00",
  "timezone": "Asia/Kolkata",
  "monitor_interval_minutes": 10,
  "clip": { "min_seconds": 20, "max_seconds": 60, "crop": "center" },
  "whisper": { "model": "small", "device": "cuda" },
  "llm": { "provider": "gemini", "model": "gemini-2.0-flash" },
  "youtube": { "privacy_status": "public", "category_id": "20" },
  "storage": { "root": "./storage" },
  "max_disk_gb": 50
}
```

- **`source_channels`**: each entry has `name`, `channel_id`, `enabled`,
  `priority`. Only `enabled: true` channels are watched. `priority` (lower =
  preferred) is a tie-break for the daily publish slot. The list hot-reloads on
  the next monitor cycle without a restart.
- **Secrets** (Gemini API key, YouTube OAuth token) live outside config in a
  `.env` file / `token.json`, never committed to git.

### 2.5 Detection method — RSS

Detection uses each channel's public RSS feed
(`https://www.youtube.com/feeds/videos.xml?channel_id=...`). No API quota cost,
no key needed. Limitation: shows ~15 most recent uploads and may lag a few
minutes; livestreams appear once listed as a normal video. Acceptable for a
10-minute poll. The YouTube Data API quota is reserved for uploads.

### 2.6 Disk cleanup

After a Short is `PUBLISHED`, the large source download and intermediate files
are deleted; only the final vertical clip and DB record are kept. `max_disk_gb`
is enforced by deleting the oldest processed source files first. If disk is
still full mid-download, new downloads pause and a warning is logged.

---

## 3. Error Handling, Edge Cases & Testing

### 3.1 Failure handling (per stage)

Each video row carries `status`, `retry_count`, `last_error`.

- **Transient failures** (network, yt-dlp timeout, LLM rate-limit): retry up to
  3 times with backoff. On 4th failure → `FAILED`, logged, worker continues to
  next video. Queue never blocks.
- **Permanent failures** (deleted/private/region-locked/member-only): mark
  `FAILED` immediately with reason, skip.
- **LLM quota exhausted:** highlight ranking falls back to audio-energy +
  keyword score alone (clip still made); metadata falls back to a template
  title/desc/tags. Logged as degraded, not failed.
- **Crash/restart:** rows stuck in an in-progress state (e.g. `DOWNLOADING`)
  are reset to their last committed clean state and the stage re-runs.

### 3.2 Edge cases

| Case | Handling |
|---|---|
| Livestream still live | Skip until finished VOD (`is_live`/duration check) |
| Very long stream | Chunked transcription; enforce `max_seconds` clip |
| Nothing READY at 18:00 | Log and skip; no crash, no empty upload |
| Multiple READY at 18:00 | Publish top-ranked; tie-break channel `priority`, then oldest READY; rest stay queued |
| Duplicate video across feeds | `video_id` unique key → deduped |
| Upload rejected (quota/auth) | Clip stays `READY`, retried next 18:00; auth errors logged loudly |
| Disk full mid-download | Clean oldest processed sources; else pause + warn |
| No speech / music-only | Skip captions; still produce clip; rank via audio-energy only |

### 3.3 Testing strategy

- **Unit tests** (no network/GPU): highlight scoring, config validation, DB
  state transitions, tie-break selection, metadata template fallback.
- **Mocked integration tests** for `downloader`, `youtube`, `llm`: external
  calls stubbed; verifies pipeline wiring without real APIs or uploads.
- **`--dry-run`**: runs full pipeline on a test video but skips the actual
  YouTube upload, writing the would-be metadata to a file. Used to verify
  quality before going live.
- **`--once <url>`**: process a single URL through the full pipeline and stop —
  for fast iteration during development.

---

## 4. Tech Stack

- Python 3.12
- yt-dlp (download)
- FFmpeg (cut, crop, caption burn)
- faster-whisper (transcription; CUDA if available)
- Google Gemini free tier (LLM ranking + metadata) via a provider interface
- google-api-python-client + OAuth (YouTube upload)
- APScheduler (scheduling)
- SQLite (state)
- pytest (tests)

---

## 5. Open items for the implementation plan

- Exact SQLite schema (columns, indexes, status enum).
- Highlight scoring formula (how audio energy, keyword hits, and LLM score
  combine into a single rank).
- Caption styling defaults (font, size, outline, position) and the FFmpeg/ASS
  approach for burning them.
- Retry/backoff timings.
- Logging format and log file rotation.
