from clipforge.highlights import keyword_score, energy_score, candidate_windows, pick_best
from clipforge.transcribe import TranscriptSeg
from clipforge.llm import LLMError

def _seg(a, b, t):
    return TranscriptSeg(start=a, end=b, text=t, words=[])

def test_keyword_score_hits():
    assert keyword_score("that was insane no way") > 0
    assert keyword_score("the weather is mild") == 0

def test_energy_score_normalized():
    assert energy_score(5.0, 10.0) == 0.5
    assert energy_score(0.0, 0.0) == 0.0

def test_candidate_windows_respect_bounds():
    segs = [_seg(0, 10, "a"), _seg(10, 20, "b"), _seg(20, 70, "c")]
    wins = candidate_windows(segs, min_s=20, max_s=40)
    assert all(20 <= (w.end - w.start) <= 40 for w in wins)
    assert wins  # at least one

def test_pick_best_uses_keywords_without_llm():
    segs = [_seg(0, 25, "boring talk here"),
            _seg(25, 50, "insane clutch no way omg")]
    best = pick_best(segs, min_s=20, max_s=30)
    assert best is not None
    assert best.start >= 25 - 30  # window covers the hype segment
    assert best.score > 0

def test_pick_best_none_when_empty():
    assert pick_best([], min_s=20, max_s=30) is None

def test_pick_best_degrades_on_llm_error():
    class BadLLM:
        def generate_json(self, prompt):
            raise LLMError("quota")
        def generate_text(self, prompt):
            raise LLMError("quota")
    segs = [_seg(0, 25, "insane no way")]
    best = pick_best(segs, min_s=20, max_s=30, llm=BadLLM())
    assert best is not None  # did not crash; degraded path
