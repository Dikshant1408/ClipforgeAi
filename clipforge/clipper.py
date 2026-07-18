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
