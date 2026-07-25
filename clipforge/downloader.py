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
    return {
        "is_live": bool(info.get("is_live")),
        "was_live": bool(info.get("was_live") or info.get("live_status") == "was_live"),
        "duration": float(info.get("duration") or 0.0)
    }


class Downloader:
    def __init__(self, storage_root: str,
                 runner: Callable[[list[str]], int] = _default_runner,
                 info_fn: Callable[[str], dict] = _default_info):
        self._root = Path(storage_root)
        self._runner = runner
        self._info = info_fn

    def is_live(self, url: str) -> bool:
        try:
            return bool(self._info(url).get("is_live"))
        except Exception:
            return False

    def was_live(self, url: str) -> bool:
        try:
            return bool(self._info(url).get("was_live"))
        except Exception:
            return False

    def duration(self, url: str) -> float:
        try:
            return float(self._info(url).get("duration") or 0.0)
        except Exception:
            return 0.0

    def download(self, video_id: str, url: str) -> str:
        import sys
        # Resolve yt-dlp inside the same virtual environment as python
        venv_bin = Path(sys.executable).parent
        yt_dlp_exe = venv_bin / "yt-dlp.exe"
        if not yt_dlp_exe.exists():
            yt_dlp_exe = venv_bin / "yt-dlp"
        
        yt_dlp_path = str(yt_dlp_exe) if yt_dlp_exe.exists() else "yt-dlp"

        out_dir = self._root / "videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_id}.mp4"
        argv = [yt_dlp_path, "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                "-o", str(out_path), url]
        rc = self._runner(argv)
        if rc != 0:
            raise RuntimeError(f"yt-dlp failed (rc={rc}) for {url}")
        return str(out_path)

