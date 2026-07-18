from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TranscriptSeg:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def _default_extract_audio(video_path: str, audio_path: str) -> int:
    return subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
         audio_path]).returncode


def _default_model_factory(model_name: str, device: str):
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    return WhisperModel(model_name, device=device, compute_type=compute)


class Transcriber:
    def __init__(self, model_name: str, device: str,
                 extract_audio: Callable[[str, str], int] = _default_extract_audio,
                 model_factory: Callable[[str, str], object] = _default_model_factory):
        self._model_name = model_name
        self._device = device
        self._extract = extract_audio
        self._factory = model_factory

    def transcribe(self, video_path: str, audio_path: str) -> list[TranscriptSeg]:
        rc = self._extract(video_path, audio_path)
        if rc != 0:
            raise RuntimeError(f"audio extract failed (rc={rc})")
        model = self._factory(self._model_name, self._device)
        segments, _info = model.transcribe(audio_path, word_timestamps=True)
        out: list[TranscriptSeg] = []
        for s in segments:
            words = [Word(start=float(w.start), end=float(w.end), text=w.word)
                     for w in (s.words or [])]
            out.append(TranscriptSeg(start=float(s.start), end=float(s.end),
                                     text=s.text.strip(), words=words))
        return out
