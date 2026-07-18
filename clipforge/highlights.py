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
