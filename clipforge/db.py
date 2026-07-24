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
    discovered_at TEXT NOT NULL DEFAULT '',
    meta_title TEXT NOT NULL DEFAULT '',
    meta_description TEXT NOT NULL DEFAULT '',
    meta_tags TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_status ON videos(status);
"""


class Database:
    def __init__(self, path: str):
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        # Database schema migration for meta columns if they don't exist
        try:
            self._conn.execute("SELECT meta_title FROM videos LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE videos ADD COLUMN meta_title TEXT NOT NULL DEFAULT ''")
            self._conn.execute("ALTER TABLE videos ADD COLUMN meta_description TEXT NOT NULL DEFAULT ''")
            self._conn.execute("ALTER TABLE videos ADD COLUMN meta_tags TEXT NOT NULL DEFAULT ''")
            self._conn.commit()

    def _row_to_rec(self, r: sqlite3.Row) -> VideoRecord:
        return VideoRecord(
            video_id=r["video_id"],
            channel_id=r["channel_id"],
            channel_name=r["channel_name"],
            title=r["title"],
            url=r["url"],
            status=Status(r["status"]),
            retry_count=r["retry_count"],
            last_error=r["last_error"],
            source_path=r["source_path"],
            clip_path=r["clip_path"],
            rank_score=r["rank_score"],
            discovered_at=r["discovered_at"],
            meta_title=r["meta_title"] if "meta_title" in r.keys() else "",
            meta_description=r["meta_description"] if "meta_description" in r.keys() else "",
            meta_tags=r["meta_tags"] if "meta_tags" in r.keys() else "",
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

    def set_metadata(self, video_id: str, title: str, description: str, tags: list[str]) -> None:
        tags_str = ",".join(tags)
        self._conn.execute(
            "UPDATE videos SET meta_title=?, meta_description=?, meta_tags=? WHERE video_id=?",
            (title, description, tags_str, video_id)
        )
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
