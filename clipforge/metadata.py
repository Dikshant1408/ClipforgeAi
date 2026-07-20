from __future__ import annotations
import logging
from clipforge.models import ClipMetadata
from clipforge.llm import LLMProvider, LLMError

log = logging.getLogger("clipforge")

_MAX_TITLE = 100
_MAX_TAGS = 20


def template_metadata(video_title: str, transcript_text: str) -> ClipMetadata:
    base = (video_title or "Highlight").strip()
    title = f"{base} | VALORANT #shorts"
    if len(title) > _MAX_TITLE:
        allowed_len = _MAX_TITLE - len(" | VALORANT #shorts")
        title = f"{base[:allowed_len]} | VALORANT #shorts"

    desc = (
        "This wasn't a skit... 😭\n"
        "They actually did this naturally, and it makes the clip even funnier.\n\n"
        "Subscribe for more clips 👇\n"
        "https://www.youtube.com/@GodRikt\n\n"
        "☕ Buy me a chai:\n"
        "https://www.chai4.me/godrikt\n\n"
        "#valorant #valorantindia\n"
        "#valorantshorts #valorantclips\n"
        "#valorantfunny #valorantmemes\n"
        "#valorantmoments #valorantedit\n"
        "#valorantmontage #fpsclips\n"
        "#valorantgameplay #riotgames\n"
        "#valorantcommunity #gaming\n"
        "#trending #fyp #viralshorts\n"
        "#esports #godrikt\n"
        "#valoranthighlights #gamingclips\n\n"
        "[⚠️ TEMPLATE FALLBACK — AI metadata failed; this is static]"
    )
    tags = [
        "valorant", "valorant shorts", "valorant funny", "valorant memes",
        "valorant clips", "valorant moments", "valorant gameplay",
        "valorant highlights", "fps gaming", "gaming shorts", "riot games",
        "godrikt"
    ]
    return ClipMetadata(title=title, description=desc, tags=tags[:_MAX_TAGS])


def generate_metadata(video_title: str, transcript_text: str,
                       llm: LLMProvider = None) -> ClipMetadata:
    if llm is None:
        return template_metadata(video_title, transcript_text)
    
    prompt = (
        "You are a YouTube Shorts SEO expert for a VALORANT clip channel. "
        "Given the source title and transcript, produce the viral Short's "
        "metadata as JSON.\n"
        f"Source Video Title: {video_title}\n"
        f"Transcript snippet: {transcript_text[:1500]}\n\n"
        "Generate:\n"
        "1. 'catchy_title': a catchy title under 75 chars about the most engaging "
        "moment, with relevant emojis (do NOT add '| VALORANT #shorts', it is added for you).\n"
        "2. 'summary': ONE or TWO vivid sentences telling the story of the clip "
        "like a human would (name the player/team/agent/weapon if known, say what "
        "happened and why it's impressive). No hashtags, no section headers. "
        "Example: 'Team Secret's Sylvan completely shuts down the enemy in an "
        "unbelievable 1v1 clutch! His insane game sense and crisp aim saved the "
        "round when all hope seemed lost.'\n"
        "3. 'hashtags': 8-15 specific clip hashtags (leading #), including players, "
        "teams, agents, and moment types from THIS clip (e.g. #teamsecret #sylvan "
        "#valorantclutch), plus general ones.\n"
        "4. 'tags': up to 15 SEO tags (comma-style keywords, no #).\n\n"
        'Return ONLY JSON: {"catchy_title": "...", "summary": "...", '
        '"hashtags": ["#..."], "tags": ["..."]}'
    )
    try:
        data = llm.generate_json(prompt)
        catchy_title = str(data.get("catchy_title", "")).strip()
        summary = str(data.get("summary", "")).strip()
        hashtags_list = [str(h).strip() for h in data.get("hashtags", [])]
        tags_list = [str(t).strip() for t in data.get("tags", [])]

        if not catchy_title:
            raise LLMError("empty title")

        # Format Title: "Catchy Title | VALORANT #shorts"
        title = f"{catchy_title} | VALORANT #shorts"
        if len(title) > _MAX_TITLE:
            allowed_len = _MAX_TITLE - len(" | VALORANT #shorts")
            title = f"{catchy_title[:allowed_len]} | VALORANT #shorts"

        # Fixed brand block (links/handle are constant for this channel)
        subscribe = (
            "Subscribe for more clips 👇\n"
            "https://www.youtube.com/@GodRikt\n\n"
            "☕ Buy me a chai:\n"
            "https://www.chai4.me/godrikt"
        )
        core_hashtags = [
            "#valorant", "#valorantindia",
            "#valorantshorts", "#valorantclips",
            "#valorantfunny", "#valorantmemes",
            "#valorantmoments", "#valorantedit",
            "#valorantmontage", "#fpsclips",
            "#valorantgameplay", "#riotgames",
            "#valorantcommunity", "#gaming",
            "#trending", "#fyp", "#viralshorts",
            "#esports", "#godrikt",
            "#valoranthighlights", "#gamingclips",
        ]
        final_hashtags = list(core_hashtags)
        for h in hashtags_list:
            if not h.startswith("#"):
                h = f"#{h}"
            h_clean = h.lower().strip()
            if h_clean and h_clean not in final_hashtags:
                final_hashtags.append(h_clean)
        hash_lines = []
        for i in range(0, len(final_hashtags), 2):
            hash_lines.append(" ".join(final_hashtags[i:i + 2]))
        hash_block = "\n".join(hash_lines)

        # Description: story summary -> subscribe/chai -> hashtags (no headers)
        description = (
            f"{summary}\n\n"
            f"{subscribe}\n\n"
            f"{hash_block}"
        )

        # YouTube Tags field (max 20)
        core_tags = [
            "valorant", "valorant shorts", "valorant funny", "valorant memes",
            "valorant clips", "valorant moments", "valorant gameplay",
            "valorant highlights", "fps gaming", "gaming shorts", "riot games",
            "godrikt",
        ]
        final_tags = list(core_tags)
        for t in tags_list:
            t_clean = t.lower().strip()
            if t_clean and t_clean not in final_tags:
                final_tags.append(t_clean)
        tags = final_tags[:_MAX_TAGS]
        
        return ClipMetadata(title=title, description=description, tags=tags)
    except (LLMError, KeyError, TypeError, ValueError) as e:
        log.error(
            "LLM metadata generation FAILED (%s) for video '%s' — using "
            "static template fallback. Clip will still publish but metadata is "
            "NOT AI-generated. Fix the LLM (model/quota/key) before relying on "
            "auto-metadata.", video_title, e)
        return template_metadata(video_title, transcript_text)
