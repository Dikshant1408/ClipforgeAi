from clipforge.transcribe import Transcriber, TranscriptSeg, Word

class FakeSeg:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words

class FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word

class FakeModel:
    def transcribe(self, audio_path, word_timestamps=True):
        segs = [FakeSeg(0.0, 2.0, "hello world",
                        [FakeWord(0.0, 1.0, "hello"), FakeWord(1.0, 2.0, "world")])]
        return segs, {"language": "en"}

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
        def transcribe(self, audio_path, word_timestamps=True):
            return [], {"language": "en"}
    t = Transcriber("small", "cpu",
                    extract_audio=lambda v, a: 0,
                    model_factory=lambda m, d: EmptyModel())
    assert t.transcribe("v", "a") == []
