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

    def delete_video_files(self, video_id: str, source_path: str = "", clip_path: str = "") -> None:
        if source_path:
            try:
                p = Path(source_path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        else:
            try:
                p = self._root / "videos" / f"{video_id}.mp4"
                if p.exists():
                    p.unlink()
            except OSError:
                pass

        if clip_path:
            try:
                p = Path(clip_path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        else:
            try:
                p = self._root / "clips" / f"{video_id}.mp4"
                if p.exists():
                    p.unlink()
            except OSError:
                pass

        try:
            p = self._root / "audio" / f"{video_id}.wav"
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def cleanup_expired_files(self) -> None:
        import datetime
        try:
            c = self._db._conn.execute(
                "SELECT video_id, status, source_path, clip_path, discovered_at FROM videos "
                "WHERE (status='READY' OR status='PUBLISHED') AND (source_path<>'' OR clip_path<>'')"
            )
            rows = c.fetchall()
        except Exception:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        for r in rows:
            try:
                ts = r["discovered_at"].replace("Z", "+00:00")
                disc_dt = datetime.datetime.fromisoformat(ts)
                if disc_dt.tzinfo is None:
                    disc_dt = disc_dt.replace(tzinfo=datetime.timezone.utc)

                age = now - disc_dt
                if r["status"] == "READY" and age > datetime.timedelta(days=2):
                    self.delete_video_files(r["video_id"], r["source_path"], r["clip_path"])
                    self._db.set_paths(r["video_id"], source_path="", clip_path="")
                elif r["status"] == "PUBLISHED" and age > datetime.timedelta(days=7):
                    self.delete_video_files(r["video_id"], r["source_path"], r["clip_path"])
                    self._db.set_paths(r["video_id"], source_path="", clip_path="")
            except Exception:
                pass

    def enforce_quota(self) -> int:
        videos_dir = self._root / "videos"
        deleted = 0
        # oldest published first (published_source_paths preserves insert order
        # by discovered_at via query; sort defensively here)
        published = self._db.published_source_paths()

        # Performance optimization: cache DB records to avoid N+1 queries during sort
        rec_cache = {vid: self._db.get(vid) for vid, _ in published}
        published_by_age = sorted(
            published,
            key=lambda pair: (getattr(rec_cache.get(pair[0]), 'discovered_at', "")
                              if rec_cache.get(pair[0]) else ""))

        # Performance optimization: Calculate directory size once (O(N) file system scan),
        # then incrementally subtract file sizes during deletion rather than
        # re-calculating (O(N^2) scan) inside the loop.
        current_size_gb = dir_size_gb(str(videos_dir))

        for video_id, source_path in published_by_age:
            if current_size_gb <= self._max:
                break
            p = Path(source_path)
            if p.exists():
                try:
                    file_size_gb = p.stat().st_size / (1024 ** 3)
                    p.unlink()
                    current_size_gb -= file_size_gb
                    deleted += 1
                except OSError:
                    pass
        return deleted
