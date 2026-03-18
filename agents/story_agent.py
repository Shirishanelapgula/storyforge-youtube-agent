"""
agents/story_agent.py
Generates original moral stories with unique characters using Claude.
"""

import json
import random
import anthropic

from config.settings import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    MORAL_THEMES,
    VIDEO_FORMATS,
    BANNED_CONTENT_KEYWORDS,
)
from config.prompts import STORY_GENERATION_PROMPT, QUALITY_CHECK_PROMPT
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("story_agent")

SUPPORTED_LANGUAGES = {
    "english": {"code": "en", "gtts_lang": "en", "name": "English"},
    "hindi":   {"code": "hi", "gtts_lang": "hi", "name": "Hindi"},
    "telugu":  {"code": "te", "gtts_lang": "te", "name": "Telugu"},
}


class StoryAgent:
    """Generates fully original moral stories for YouTube videos."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    @retry(max_attempts=3, delay=5.0)
    def generate_story(
        self,
        format_type: str = "long",
        theme: str = None,
        language: str = "english",
    ) -> dict:
        """
        Generate a complete story with characters and scenes.

        Args:
            format_type: "shorts" or "long"
            theme: Optional theme override; random if None
            language: "english", "hindi", or "telugu"

        Returns:
            Story dict with title, characters, scenes, metadata
        """
        theme = theme or random.choice(MORAL_THEMES)
        scene_count = VIDEO_FORMATS[format_type]["target_scenes"]
        lang_info = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES["english"])
        lang_name = lang_info["name"]

        logger.info(
            f"Generating {format_type} story | "
            f"theme='{theme}' | language='{lang_name}'"
        )

        prompt = STORY_GENERATION_PROMPT.format(
            format_type=format_type,
            theme=theme,
            scene_count=scene_count,
        )

        if language != "english":
            prompt += (
                f"\n\nIMPORTANT: Write the ENTIRE story — all narration text, "
                f"character names, scene titles, moral, description, "
                f"call_to_action, and tags — in {lang_name} language only. "
                f"Do NOT use English anywhere in the output."
            )

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        story = json.loads(raw.strip())
        story["format_type"] = format_type
        story["theme"] = theme
        story["language"] = language

        logger.info(f"Story generated: '{story.get('title', 'Untitled')}'")
        self._validate_story(story)
        return story

    def _validate_story(self, story: dict) -> None:
        """Basic content guard before sending to quality check."""
        full_text = json.dumps(story).lower()
        for keyword in BANNED_CONTENT_KEYWORDS:
            if keyword in full_text:
                raise ValueError(
                    f"Story contains banned keyword '{keyword}'. Regenerating."
                )

        required_keys = ["title", "moral", "scenes", "characters"]
        for key in required_keys:
            if key not in story:
                raise ValueError(f"Story missing required field: '{key}'")

        if not story["scenes"]:
            raise ValueError("Story has no scenes.")

        logger.debug("Story passed local validation.")

    @retry(max_attempts=2, delay=3.0)
    def quality_check(self, story: dict) -> dict:
        """
        Run story through Claude for YouTube monetization compliance check.

        Returns:
            {"approved": bool, "score": float, "issues": list, "notes": str}
        """
        logger.info(f"Running quality check for: '{story.get('title')}'")

        content_preview = (
            story.get("title", "") + " " +
            story.get("moral", "") + " " +
            " ".join(s.get("narration", "") for s in story.get("scenes", []))
        )[:2000]

        prompt = QUALITY_CHECK_PROMPT.format(
            title=story.get("title"),
            content=content_preview,
        )

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw.strip())
        logger.info(
            f"Quality check result: approved={result.get('approved')} "
            f"score={result.get('score')}"
        )
        return result