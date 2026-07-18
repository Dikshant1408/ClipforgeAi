from clipforge.metadata import generate_metadata, template_metadata
from clipforge.models import ClipMetadata
from clipforge.llm import LLMError

def test_template_metadata():
    m = template_metadata("Cool Stream", "we did an insane play")
    assert isinstance(m, ClipMetadata)
    assert m.title
    assert m.tags

def test_generate_with_llm():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "Insane Play!", "description": "wow",
                    "tags": ["gaming", "shorts"]}
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert m.title == "Insane Play!"
    assert "gaming" in m.tags

def test_generate_degrades_on_error():
    class LLM:
        def generate_json(self, prompt):
            raise LLMError("quota")
        def generate_text(self, prompt):
            raise LLMError("quota")
    m = generate_metadata("Backup Title", "txt", llm=LLM())
    assert isinstance(m, ClipMetadata)
    assert m.title  # from template

def test_title_truncated_to_100():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "x" * 200, "description": "d", "tags": []}
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.title) <= 100

def test_tags_capped_at_20():
    class LLM:
        def generate_json(self, prompt):
            return {"title": "t", "description": "d",
                    "tags": [f"t{i}" for i in range(50)]}
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.tags) <= 20
