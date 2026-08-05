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


def make_wav_energy_func(wav_path: str) -> Callable[[float, float], float]:
    import wave
    import numpy as np

    # Pre-compute the energy for the entire file in chunks using a cumulative
    # sum array. This prevents O(N^2) file I/O operations and drops time
    # complexity of the energy lookup to O(1) for each candidate window.
    try:
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            if w.getsampwidth() != 2:
                return lambda s, e: 0.0

            chunk_duration = 0.1
            chunk_frames = int(sr * chunk_duration)

            chunk_sq_sums = []
            chunk_counts = []

            while True:
                frames = w.readframes(chunk_frames)
                if not frames:
                    break
                samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                chunk_sq_sums.append(np.sum(samples ** 2))
                chunk_counts.append(len(samples))

            cum_sq = np.concatenate(([0.0], np.cumsum(chunk_sq_sums)))
            cum_count = np.concatenate(([0], np.cumsum(chunk_counts)))
            num_chunks = len(chunk_sq_sums)
    except Exception:
        return lambda s, e: 0.0

    def energy_func(start: float, end: float) -> float:
        start_chunk = int(start / chunk_duration)
        end_chunk = int(np.ceil(end / chunk_duration))

        start_chunk = max(0, min(start_chunk, num_chunks))
        end_chunk = max(0, min(end_chunk, num_chunks))

        if start_chunk >= end_chunk:
            return 0.0

        sq_sum = cum_sq[end_chunk] - cum_sq[start_chunk]
        count = cum_count[end_chunk] - cum_count[start_chunk]

        if count == 0:
            return 0.0

        return float(np.sqrt(sq_sum / count))

    return energy_func


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


def pad_hook(seg: Segment, segments: list[TranscriptSeg], lead: float,
             min_s: float) -> Segment:
    """Start the clip a little BEFORE the highlight so the action lands in the
    first ~2s instead of after dead buildup. Never go before t=0."""
    if lead <= 0:
        return seg
    new_start = max(0.0, seg.start - lead)
    if (seg.end - new_start) < min_s:
        # extend the end to honour the minimum length
        new_end = seg.end + (min_s - (seg.end - new_start))
        seg = Segment(start=new_start, end=new_end, score=seg.score,
                      reason=seg.reason)
    else:
        seg = Segment(start=new_start, end=seg.end, score=seg.score,
                      reason=seg.reason)
    return seg


def pick_best(segments: list[TranscriptSeg], min_s: float, max_s: float,
              llm: LLMProvider = None,
              energy: Callable[[float, float], float] = None,
              hook_lead: float = 0.0) -> Segment | None:
    if not segments:
        return None
    windows = candidate_windows(segments, min_s, max_s)
    if not windows:
        return None
    if energy is not None:
        rms_vals = []
        for w in windows:
            rms_vals.append(energy(w.start, w.end))
        max_rms = max(rms_vals) if rms_vals else 0.0
        if max_rms > 0.0:
            for idx, w in enumerate(windows):
                w.score += energy_score(rms_vals[idx], max_rms) * 0.5
    # boost the LLM-chosen window if available
    if llm is not None:
        try:
            idx = _llm_rank(llm, windows, segments)
            if idx is not None:
                windows[idx].score += 1.0
        except LLMError:
            pass  # degrade to keyword-only scoring
    windows.sort(key=lambda w: (w.score, -(w.end - w.start)), reverse=True)
    best = windows[0]
    return pad_hook(best, segments, hook_lead, min_s)
