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
Style: Default,Arial,84,&H00FFFFFF,&H00000000,&H64000000,-1,1,5,1,2,80,80,260,1
Style: Hook,Arial,108,&H00FFFFFF,&H00000000,&HAA000000,-1,3,8,2,5,80,80,170,1

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


def _karaoke_line(words, seg_start: float, seg_end: float, line_start: float,
                  line_end: float) -> str | None:
    """Build one ASS Dialogue line that paints each word progressively using the
    {\\k<dur>} karaoke tag, so the spoken word highlights in sync."""
    in_window = [w for w in words
                 if w.end > seg_start and w.start < seg_end]
    if not in_window:
        return None
    parts: list[str] = []
    for w in in_window:
        w_start = max(w.start, seg_start)
        w_end = min(w.end, seg_end)
        dur_cs = max(1, int(round((w_end - w_start) * 100)))
        text = w.text.strip()
        if not text:
            continue
        parts.append(f"{{\\k{dur_cs}}}{text}")
    if not parts:
        return None
    centered = "\\an2"
    karaoke = "".join(parts)
    return (f"Dialogue: 0,{format_timestamp(line_start)},"
            f"{format_timestamp(line_end)},Default,,0,0,0,,"
            f"{centered}{karaoke}")


def build_ass(segments: list[TranscriptSeg], seg_start: float,
              seg_end: float, hook_text: str = "") -> str:
    lines = [_ASS_HEADER]

    # Bold hook overlay: large centered text for the first ~2.5s (pattern
    # interrupt). Sits above the captions.
    hook_dur = 2.5
    hook_end = min(hook_dur, seg_end - seg_start)
    if hook_text and hook_end > 0:
        hook_clean = hook_text.replace("\n", " ").strip().replace("\\", "\\\\")
        lines.append(
            f"Dialogue: 1,0:00:00.00,{format_timestamp(hook_end)},"
            f"Hook,,0,0,0,,{hook_clean}")

    for s in segments:
        if s.end <= seg_start or s.start >= seg_end:
            continue
        line_start = max(s.start, seg_start) - seg_start
        line_end = min(s.end, seg_end) - seg_start
        line = _karaoke_line(s.words, seg_start, seg_end, line_start, line_end)
        if line:
            lines.append(line)
            continue
        text = s.text.replace("\n", " ").strip()
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{format_timestamp(line_start)},"
            f"{format_timestamp(line_end)},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def _default_runner(argv: list[str]) -> int:
    return subprocess.run(argv).returncode


class Clipper:
    def __init__(self, storage_root: str,
                 runner: Callable[[list[str]], int] = _default_runner):
        self._root = Path(storage_root)
        self._runner = runner

    def make_short(self, video_id: str, source_path: str, seg: Segment,
                   transcript: list[TranscriptSeg],
                   hook_text: str = "") -> str:
        clips_dir = self._root / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        ass_path = clips_dir / f"{video_id}.ass"
        ass_path.write_text(
            build_ass(transcript, seg.start, seg.end, hook_text=hook_text),
            encoding="utf-8")
        out_path = clips_dir / f"{video_id}.mp4"
        # center-crop to 9:16, subtle slow zoom-punch (Ken Burns).
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
