from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Callable
from clipforge.models import Segment


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv).returncode


class Clipper:
    def __init__(self, storage_root: str,
                 runner: Callable[[list[str]], int] = _default_runner):
        self._root = Path(storage_root)
        self._runner = runner

    def make_short(self, video_id: str, source_path: str, seg: Segment,
                   transcript: list[dict]) -> str:
        clips_dir = self._root / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        out_path = clips_dir / f"{video_id}.mp4"
        # center-crop to 9:16, subtle slow zoom-punch (Ken Burns).
        # No burned-in subtitles — YouTube auto-generates captions from audio.
        vf = ("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',"
              "scale=1080:1920,"
              "zoompan=z='min(zoom+0.0008,1.12)':d=1:x='iw/2-(iw/zoom/2)':"
              "y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30")
        argv = ["ffmpeg", "-y", "-i", source_path,
                "-ss", str(seg.start), "-to", str(seg.end),
                "-avoid_negative_ts", "make_zero",
                "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", str(out_path)]
        rc = self._runner(argv)
        if rc != 0:
            raise RuntimeError(f"ffmpeg clip failed (rc={rc})")
        return str(out_path)
