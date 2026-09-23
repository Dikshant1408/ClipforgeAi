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
    from functools import lru_cache

    CHUNK_DUR = 60.0 # 60 seconds chunks

    @lru_cache(maxsize=8)
    def _get_chunk(chunk_idx: int) -> tuple[np.ndarray, int, int]:
        try:
            with wave.open(wav_path, "rb") as w:
                sr = w.getframerate()
                nchannels = w.getnchannels()
                if w.getsampwidth() != 2:
                    return np.array([], dtype=np.float64), sr, nchannels

                start_frame = int(chunk_idx * CHUNK_DUR * sr)
                if start_frame >= w.getnframes():
                    return np.array([], dtype=np.float64), sr, nchannels

                w.setpos(start_frame)
                frames_to_read = int(CHUNK_DUR * sr)
                data = w.readframes(frames_to_read)

                samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                # Precompute cumulative sum of squared samples for O(1) interval queries
                cumsum = np.cumsum(samples ** 2)
                # Add 0 at the beginning to handle queries starting at index 0 correctly
                cumsum = np.insert(cumsum, 0, 0.0)
                return cumsum, sr, nchannels
        except Exception:
            return np.array([], dtype=np.float64), 44100, 1

    def energy_func(start: float, end: float) -> float:
        try:
            chunk_idx = int(start // CHUNK_DUR)
            cumsum, sr, nchannels = _get_chunk(chunk_idx)
            if len(cumsum) <= 1:
                return 0.0

            chunk_start_time = chunk_idx * CHUNK_DUR

            # Start and end frame relative to the chunk
            start_frame = int((start - chunk_start_time) * sr) * nchannels
            end_frame = int((end - chunk_start_time) * sr) * nchannels

            start_frame = max(0, min(start_frame, len(cumsum) - 1))
            end_frame = max(0, min(end_frame, len(cumsum) - 1))

            if start_frame >= end_frame:
                return 0.0

            # O(1) query using cumulative sum
            sum_sq = cumsum[end_frame] - cumsum[start_frame]
            mean_sq = sum_sq / (end_frame - start_frame)
            return float(np.sqrt(mean_sq))
        except Exception:
            return 0.0

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
