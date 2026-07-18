from __future__ import annotations
from clipforge.models import ClipMetadata
from clipforge.llm import LLMProvider, LLMError

_MAX_TITLE = 100
_MAX_TAGS = 20


def template_metadata(video_title: str, transcript_text: str) -> ClipMetadata:
    base = (video_title or "Highlight").strip()[:_MAX_TITLE]
    title = base if base else "Highlight"
    desc = f"Clip from: {video_title}\n\n#shorts"
    tags = ["shorts", "clip", "highlights", "viral", "trending"]
    return ClipMetadata(title=title, description=desc, tags=tags[:_MAX_TAGS])


def generate_metadata(video_title: str, transcript_text: str,
                       llm: LLMProvider = None) -> ClipMetadata:
    if llm is None:
        return template_metadata(video_title, transcript_text)
    prompt = (
        "You are a YouTube Shorts SEO expert. Given this clip transcript, "
        "produce a viral Short's metadata.\n"
        f"Source video title: {video_title}\n"
        f"Transcript: {transcript_text[:2000]}\n\n"
        'Return JSON only: {"title": "<=100 chars, catchy", '
        '"description": "2-3 lines + hashtags", "tags": ["up to 20"]}'
    )
    try:
        data = llm.generate_json(prompt)
        title = str(data["title"])[:_MAX_TITLE]
        desc = str(data["description"])
        tags = [str(t) for t in data.get("tags", [])][:_MAX_TAGS]
        if not title:
            raise LLMError("empty title")
        return ClipMetadata(title=title, description=desc, tags=tags)
    except (LLMError, KeyError, TypeError):
        return template_metadata(video_title, transcript_text)
