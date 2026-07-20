from clipforge.metadata import generate_metadata, template_metadata
from clipforge.models import ClipMetadata
from clipforge.llm import LLMError

def test_template_metadata():
    m = template_metadata("Cool Stream", "we did an insane play")
    assert isinstance(m, ClipMetadata)
    assert m.title
    assert m.tags

def test_template_metadata_uses_exact_format():
    m = template_metadata("Cool Stream", "we did an insane play")
    assert "🔥" not in m.description and "📝" not in m.description
    assert "Subscribe for more clips 👇" in m.description
    assert "https://www.chai4.me/godrikt" in m.description
    assert "#valorant" in m.description

def test_ai_metadata_uses_exact_format():
    class LLM:
        def generate_json(self, prompt):
            return {
                "catchy_title": "Insane Play!",
                "summary": "they actually did this naturally 😭",
                "hashtags": ["#gaming", "#shorts"],
                "tags": ["gaming", "shorts"],
            }
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert m.title == "Insane Play! | VALORANT #shorts"
    assert "🔥" not in m.description and "📝" not in m.description
    assert "Insane Play! | VALORANT #shorts" not in m.description  # title not repeated in desc
    assert "they actually did this naturally 😭" in m.description
    assert "Subscribe for more clips 👇" in m.description
    assert "gaming" in m.tags
    assert "#gaming" in m.description  # hashtags still in description

def test_generate_with_llm():
    class LLM:
        def generate_json(self, prompt):
            return {
                "catchy_title": "Insane Play!", 
                "summary": "wow",
                "hashtags": ["#gaming", "#shorts"],
                "tags": ["gaming", "shorts"]
            }
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert m.title == "Insane Play! | VALORANT #shorts"
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
            return {
                "catchy_title": "x" * 200, 
                "summary": "d", 
                "hashtags": [],
                "tags": []
            }
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.title) <= 100

def test_tags_capped_at_20():
    class LLM:
        def generate_json(self, prompt):
            return {
                "catchy_title": "t", 
                "summary": "d",
                "hashtags": [],
                "tags": [f"t{i}" for i in range(50)]
            }
        def generate_text(self, prompt):
            return ""
    m = generate_metadata("t", "txt", llm=LLM())
    assert len(m.tags) <= 20
