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
