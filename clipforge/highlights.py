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

    try:
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            sampwidth = w.getsampwidth()
            nchannels = w.getnchannels()
            nframes = w.getnframes()
    except Exception:
        return lambda s, e: 0.0

    if sampwidth != 2:
        return lambda s, e: 0.0

    chunk_duration = 30.0 # seconds
    chunk_frames = int(chunk_duration * sr)

    @lru_cache(maxsize=32)
    def get_chunk(chunk_idx: int) -> np.ndarray:
        try:
            with wave.open(wav_path, "rb") as w:
                start_frame = chunk_idx * chunk_frames
                if start_frame >= nframes:
                    return np.array([0.0], dtype=np.float64)
                w.setpos(start_frame)
                frames_to_read = min(chunk_frames, nframes - start_frame)
                data = w.readframes(frames_to_read)
                # Cast to float64 to prevent precision loss in large cumsums
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float64)
                sq = samples ** 2
                cumsum = np.zeros(len(sq) + 1, dtype=np.float64)
                np.cumsum(sq, out=cumsum[1:])
                return cumsum
        except Exception:
            return np.array([0.0], dtype=np.float64)

    def energy_func(start: float, end: float) -> float:
        # Calculate RMS energy for [start, end] leveraging pre-computed chunk cumsums
        start_f = int(start * sr)
        end_f = int(end * sr)
        if start_f >= nframes:
            return 0.0
        end_f = min(end_f, nframes)
        if start_f >= end_f:
            return 0.0

        total_sq = 0.0
        total_samples = (end_f - start_f) * nchannels

        start_chunk = start_f // chunk_frames
        end_chunk = end_f // chunk_frames

        for c in range(start_chunk, end_chunk + 1):
            c_start_f = c * chunk_frames
            c_end_f = min(c_start_f + chunk_frames, nframes)

            i_start = max(start_f, c_start_f)
            i_end = min(end_f, c_end_f)
            if i_start < i_end:
                cumsum = get_chunk(c)
                idx_start = (i_start - c_start_f) * nchannels
                idx_end = (i_end - c_start_f) * nchannels

                idx_end = min(idx_end, len(cumsum) - 1)
                idx_start = min(idx_start, len(cumsum) - 1)

                total_sq += cumsum[idx_end] - cumsum[idx_start]

        if total_samples <= 0:
            return 0.0
        return float(np.sqrt(total_sq / total_samples))

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
