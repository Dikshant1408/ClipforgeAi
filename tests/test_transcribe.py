from clipforge.transcribe import Transcriber, TranscriptSeg, Word

class FakeSeg:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words

class FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word

class FakeModel:
    def transcribe(self, audio_path, word_timestamps=True, language=None, task="transcribe"):
        segs = [FakeSeg(0.0, 2.0, "hello world",
                        [FakeWord(0.0, 1.0, "hello"), FakeWord(1.0, 2.0, "world")])]
        class _I: pass
        i = _I(); i.language = "en"
        return segs, i

def test_transcribe_maps_segments(tmp_path):
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: FakeModel())
    out = t.transcribe(str(tmp_path / "v.mp4"), str(tmp_path / "a.wav"))
    assert len(out) == 1
    assert isinstance(out[0], TranscriptSeg)
    assert out[0].text == "hello world"
    assert out[0].words[0].text == "hello"

def test_transcribe_empty_returns_empty(tmp_path):
    class EmptyModel:
        def transcribe(self, audio_path, word_timestamps=True, language=None, task="transcribe"):
            class _I: pass
            i = _I(); i.language = "en"
            return [], i
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: EmptyModel())
    assert t.transcribe("v", "a") == []


def test_transcribe_forwards_language_to_model(tmp_path):
    captured = {}
    class Model:
        def transcribe(self, audio_path, word_timestamps=True, language=None, task="transcribe"):
            captured["language"] = language
            captured["task"] = task
            class _I: pass
            i = _I(); i.language = language or "en"
            return [], i
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: Model(),
                    language="ko")
    t.transcribe("v", "a")
    assert captured["language"] == "ko"
    assert captured["task"] == "transcribe"


def test_transcribe_no_language_defaults_to_auto():
    captured = {}
    class Model:
        def transcribe(self, audio_path, word_timestamps=True, language=None, task="transcribe"):
            captured["language"] = language
            captured["task"] = task
            class _I: pass
            i = _I(); i.language = "en"
            return [], i
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: Model())
    t.transcribe("v", "a")
    assert captured["language"] is None
    assert captured["task"] == "transcribe"
