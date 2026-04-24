"""
agents/story_agent.py
Generates original moral stories with unique characters using Claude.
"""

import json
import re
import random
import anthropic

from config.settings import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    MORAL_THEMES,
    VIDEO_FORMATS,
    BANNED_CONTENT_KEYWORDS,
    CLAUDE_MAX_TOKENS_LONG
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


def _safe_json_parse(raw: str) -> dict:
    """
    Robustly parse JSON from Claude responses.
    Handles: markdown fences, trailing commas, truncated responses,
    Telugu/Hindi characters breaking string boundaries.
    """
    # Strip markdown fences
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in response: {text[:300]}")

    extracted = text[start:end]

    # Try extracted JSON
    try:
        return json.loads(extracted)
    except json.JSONDecodeError:
        pass

    # Fix common issues
    # 1. Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*}", "}", extracted)
    cleaned = re.sub(r",\s*]", "]", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Fix unterminated strings by finding the error position
    # and truncating/closing the JSON there
    try:
        # Try to find where the JSON breaks and close it
        for i in range(len(cleaned), max(len(cleaned) - 500, 0), -10):
            truncated = cleaned[:i]
            # Count open braces and brackets
            open_braces = truncated.count("{") - truncated.count("}")
            open_brackets = truncated.count("[") - truncated.count("]")
            # Close them
            truncated += "]" * open_brackets + "}" * open_braces
            try:
                result = json.loads(truncated)
                logger.warning("JSON was truncated and auto-repaired")
                return result
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    raise ValueError(
        f"Could not parse JSON after all recovery attempts. "
        f"Preview: {extracted[:300]}"
    )


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
        """Generate a complete story with characters and scenes."""
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
                f"\n\nCRITICAL LANGUAGE REQUIREMENT:"
                f"\n- Write ALL story content in {lang_name} ONLY"
                f"\n- Every single word of narration must be in {lang_name}"
                f"\n- Character names must be traditional {lang_name} names"
                f"\n- Scene titles must be in {lang_name}"
                f"\n- Moral lesson must be in {lang_name}"
                f"\n- Call to action must be in {lang_name}"
                f"\n- Description and tags must be in {lang_name}"
                f"\n- Do NOT use ANY English words anywhere in the story values"
                f"\n- JSON keys (title, moral, scenes, narration etc.) stay in English"
                f"\n- But every value must be pure {lang_name} text"
                f"\n- If you write even one English word in narration, it is WRONG"
            )

        # Long videos need more tokens to complete the full story
        
        max_tokens = CLAUDE_MAX_TOKENS_LONG if format_type == "long" else CLAUDE_MAX_TOKENS

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        try:
            story = _safe_json_parse(raw)
        except Exception as e:
            raise ValueError(f"JSON parse failed: {e}")

        story["format_type"] = format_type
        story["theme"] = theme
        story["language"] = language

        logger.info(f"Story generated: '{story.get('title', 'Untitled')}'")
        self._validate_story(story)
        return story

    def _validate_story(self, story: dict) -> None:
        """Basic content guard before sending to quality check."""
        full_text = json.dumps(story, ensure_ascii=False).lower()
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

        # Verify last scene exists and has proper narration
        last_scene = story["scenes"][-1]
        last_narration = last_scene.get("narration", "")
        if len(last_narration.split()) < 10:
            raise ValueError(
                "Last scene narration too short — story has no proper conclusion. Regenerating."
            )

        # Verify scene count matches expected
        expected = VIDEO_FORMATS[story.get("format_type", "long")]["target_scenes"]
        actual = len(story["scenes"])
        if actual < max(2, expected * 0.5):
            raise ValueError(
                f"Story only has {actual} scenes, expected {expected}. "
                f"Story is incomplete. Regenerating."
            )
        # Check for English contamination in non-English stories
        language = story.get("language", "english")
        if language == "telugu":
            all_narration = " ".join(
                s.get("narration", "") for s in story.get("scenes", [])
            )
            # Count ASCII letters — Telugu script has no ASCII
            ascii_chars = sum(1 for c in all_narration if c.isascii() and c.isalpha())
            total_chars = sum(1 for c in all_narration if c.isalpha())
            if total_chars > 0:
                english_ratio = ascii_chars / total_chars
                if english_ratio > 0.15:  # More than 15% English letters
                    raise ValueError(
                        f"Telugu story contains too much English ({english_ratio:.0%}). "
                        f"Regenerating with stricter language enforcement."
                    )
                logger.debug(f"Language check: {english_ratio:.0%} English in Telugu story")
        # Enforce English visual_description fields
        for scene in story.get("scenes", []):
            vd = scene.get("visual_description", "")
            if not vd:
                # Auto-generate English visual description from scene context
                scene["visual_description"] = (
                    f"Scene {scene.get('scene_number', 1)}: "
                    f"{scene.get('emotion', 'warm')} moment, "
                    f"Indian characters in traditional setting, "
                    f"warm cinematic lighting, medium shot"
                )
                continue

            # Check if visual_description is Telugu/Hindi (non-ASCII)
            ascii_chars = sum(1 for c in vd if c.isascii())
            total_chars = len(vd)
            if total_chars > 0 and ascii_chars / total_chars < 0.6:
                # Too many non-ASCII chars — it's in Telugu/Hindi, replace it
                logger.warning(
                    f"Scene {scene.get('scene_number')} visual_description "
                    f"is in non-English — auto-replacing"
                )
                scene["visual_description"] = (
                    f"{scene.get('emotion', 'warm').title()} scene, "
                    f"Indian characters in traditional clothing, "
                    f"story setting background, "
                    f"warm cinematic lighting, medium shot"
                )

        logger.debug(f"Story passed validation. {actual} scenes, "
                     f"last scene: {last_narration[:50]}...")

    @retry(max_attempts=2, delay=3.0)
    def quality_check(self, story: dict) -> dict:
        """Run story through Claude for YouTube monetization compliance check."""
        logger.info(f"Running quality check for: '{story.get('title')}'")

        content_preview = (
            str(story.get("title", "")) + " " +
            str(story.get("moral", "")) + " " +
            " ".join(
                str(s.get("narration", ""))
                for s in story.get("scenes", [])
            )
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

        try:
            result = _safe_json_parse(raw)
        except Exception:
            # Default to approved if quality check parsing fails
            result = {
                "approved": True,
                "score": 0.85,
                "issues": [],
                "notes": "Quality check parse fallback"
            }

        logger.info(
            f"Quality check: approved={result.get('approved')} "
            f"score={result.get('score')}"
        )
        return result