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
    """Creates a function to calculate RMS energy of a wave file over a time range.
    Optimized with chunked lru_cache and O(1) cumsum lookups to avoid overlapping reads."""
    import wave
    import numpy as np
    from functools import lru_cache

    try:
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            sampwidth = w.getsampwidth()
            nchannels = w.getnchannels()
            nframes = w.getnframes()
    except Exception:
        return lambda start, end: 0.0

    if sampwidth != 2:
        return lambda start, end: 0.0

    # Read the audio in chunks of 60 seconds
    CHUNK_S = 60.0
    CHUNK_FRAMES = int(CHUNK_S * sr)
    CHUNK_SAMPLES = CHUNK_FRAMES * nchannels

    # Cache recent chunks. We use 8 to keep memory low (8 * 60s * 48kHz * 2ch * 8bytes ~ 3.6MB per chunk)
    @lru_cache(maxsize=8)
    def get_chunk_cumsum(chunk_idx: int) -> np.ndarray:
        try:
            with wave.open(wav_path, "rb") as w:
                start_frame = chunk_idx * CHUNK_FRAMES
                if start_frame >= nframes:
                    return np.array([0.0], dtype=np.float64)
                w.setpos(start_frame)
                frames_to_read = min(CHUNK_FRAMES, nframes - start_frame)
                data = w.readframes(frames_to_read)
                samples = np.frombuffer(data, dtype=np.int16)

                # Must use float64 for sum of squares to prevent severe precision loss on large arrays
                sq = samples.astype(np.float64) ** 2

                # Pre-compute cumulative sums to allow O(1) queries for any sub-segment
                cs = np.empty(len(sq) + 1, dtype=np.float64)
                cs[0] = 0.0
                np.cumsum(sq, out=cs[1:])
                return cs
        except Exception:
            return np.array([0.0], dtype=np.float64)

    def energy_func(start: float, end: float) -> float:
        try:
            start_frame = int(start * sr)
            end_frame = int(end * sr)
            if start_frame >= nframes:
                return 0.0
            end_frame = min(end_frame, nframes)

            # Convert frame indices to sample indices (multiplying by channels is crucial for multi-channel)
            start_sample = start_frame * nchannels
            end_sample = end_frame * nchannels

            if end_sample <= start_sample:
                return 0.0

            total_sq = 0.0
            curr_sample = start_sample

            # Query chunks to cover the requested range
            while curr_sample < end_sample:
                chunk_idx = curr_sample // CHUNK_SAMPLES
                chunk_start_sample = chunk_idx * CHUNK_SAMPLES

                local_start = curr_sample - chunk_start_sample
                local_end = min(end_sample - chunk_start_sample, CHUNK_SAMPLES)

                cs = get_chunk_cumsum(chunk_idx)

                if len(cs) <= local_start:
                    break

                actual_local_end = min(local_end, len(cs) - 1)
                if actual_local_end > local_start:
                    # O(1) sum calculation over the segment via cumulative sum difference
                    total_sq += (cs[actual_local_end] - cs[local_start])

                curr_sample += (actual_local_end - local_start)

                if actual_local_end < local_end:
                    break

            actual_samples_read = curr_sample - start_sample
            if actual_samples_read <= 0:
                return 0.0

            return float(np.sqrt(total_sq / actual_samples_read))
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
