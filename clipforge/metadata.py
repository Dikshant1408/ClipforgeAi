from __future__ import annotations
from clipforge.models import ClipMetadata
from clipforge.llm import LLMProvider, LLMError

_MAX_TITLE = 100
_MAX_TAGS = 20


def template_metadata(video_title: str, transcript_text: str) -> ClipMetadata:
    base = (video_title or "Highlight").strip()
    title = f"{base} | VCT VALORANT #shorts"
    if len(title) > _MAX_TITLE:
        allowed_len = _MAX_TITLE - len(" | VCT VALORANT #shorts")
        title = f"{base[:allowed_len]} | VCT VALORANT #shorts"
        
    desc = (
        "Check out this epic VCT VALORANT highlight!\n"
        "Awesome play and intense moments.\n\n"
        "Subscribe for more clips 👇\n"
        "https://www.youtube.com/@GodRikt\n\n"
        "☕ Buy me a chai:\n"
        "https://www.chai4.me/godrikt\n\n"
        "#valorant #vct #godrikt #shorts"
    )
    tags = ["valorant", "vct", "godrikt", "valorant shorts", "valorant clips"]
    return ClipMetadata(title=title, description=desc, tags=tags[:_MAX_TAGS])


def generate_metadata(video_title: str, transcript_text: str,
                       llm: LLMProvider = None) -> ClipMetadata:
    if llm is None:
        return template_metadata(video_title, transcript_text)
    
    prompt = (
        "You are a YouTube Shorts SEO expert. Given this clip details and transcript, "
        "produce the viral Short's metadata components in JSON format.\n"
        f"Source Video Title: {video_title}\n"
        f"Transcript snippet: {transcript_text[:1500]}\n\n"
        "Your task is to generate:\n"
        "1. A catchy title (under 75 characters) focused on the most engaging part. It should include relevant emojis.\n"
        "2. A 2-line summary explaining the emotional, funny, or key moment (to be used at the top of the description).\n"
        "3. A list of 5-8 relevant hashtags related to the content.\n"
        "4. A list of up to 15 relevant tags (comma-separated style keywords).\n\n"
        "Return ONLY a JSON object with this exact structure:\n"
        "{\n"
        '  "catchy_title": "Title text here",\n'
        '  "summary": "2-line summary explaining the clip.",\n'
        '  "hashtags": ["#tag1", "#tag2", ...],\n'
        '  "tags": ["tag1", "tag2", ...]\n'
        "}"
    )
    try:
        data = llm.generate_json(prompt)
        catchy_title = str(data.get("catchy_title", "")).strip()
        summary = str(data.get("summary", "")).strip()
        hashtags_list = [str(h).strip() for h in data.get("hashtags", [])]
        tags_list = [str(t).strip() for t in data.get("tags", [])]
        
        if not catchy_title:
            raise LLMError("empty title")
            
        # Format Title: "Catchy Title | VCT VALORANT #shorts"
        title = f"{catchy_title} | VCT VALORANT #shorts"
        if len(title) > _MAX_TITLE:
            allowed_len = _MAX_TITLE - len(" | VCT VALORANT #shorts")
            title = f"{catchy_title[:allowed_len]} | VCT VALORANT #shorts"
            
        # Format Description
        desc_parts = [
            summary,
            "",
            "Subscribe for more clips 👇",
            "https://www.youtube.com/@GodRikt",
            "",
            "☕ Buy me a chai:",
            "https://www.chai4.me/godrikt",
            ""
        ]
        
        # Ensure core hashtags are included
        final_hashtags = ["#valorant", "#vct", "#godrikt", "#shorts"]
        for h in hashtags_list:
            if not h.startswith("#"):
                h = f"#{h}"
            h_clean = h.lower()
            if h_clean not in final_hashtags:
                final_hashtags.append(h_clean)
        desc_parts.append("\n".join(final_hashtags[:20]))
        description = "\n".join(desc_parts)
        
        # Format Tags
        final_tags = ["valorant", "vct", "godrikt", "valorant shorts", "valorant clips"]
        for t in tags_list:
            t_clean = t.lower().strip()
            if t_clean and t_clean not in final_tags:
                final_tags.append(t_clean)
        tags = final_tags[:_MAX_TAGS]
        
        return ClipMetadata(title=title, description=description, tags=tags)
    except Exception:
        return template_metadata(video_title, transcript_text)
