import pytest
from clipforge.llm import GeminiProvider, get_provider, LLMError, LLMProvider

class FakeResp:
    def __init__(self, text):
        self.text = text

class FakeModel:
    def __init__(self, text):
        self._text = text
    def generate_content(self, prompt):
        return FakeResp(self._text)

def _provider(text):
    return GeminiProvider("gemini-2.0-flash", "key",
                          client_factory=lambda m, k: FakeModel(text))

def test_generate_json_plain():
    p = _provider('{"a": 1}')
    assert p.generate_json("x") == {"a": 1}

def test_generate_json_fenced():
    p = _provider('```json\n{"a": 2}\n```')
    assert p.generate_json("x") == {"a": 2}

def test_generate_json_bad_raises():
    p = _provider("not json")
    with pytest.raises(LLMError):
        p.generate_json("x")

def test_generate_text():
    p = _provider("hello")
    assert p.generate_text("x") == "hello"

def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nope", "m", "k")

def test_factory_returns_provider():
    assert isinstance(get_provider("gemini", "gemini-2.0-flash", "k"), LLMProvider)
