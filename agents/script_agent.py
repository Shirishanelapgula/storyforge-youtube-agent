"""
agents/script_agent.py
Processes story data into structured narration scripts per scene.
"""

import json
from pathlib import Path

from utils.logger import get_logger
from utils.file_utils import save_json

logger = get_logger("script_agent")


class ScriptAgent:
    """Converts raw story JSON into structured per-scene scripts."""

    def build_scripts(self, story: dict, workspace: Path) -> list[dict]:
        """
        Build narration script for each scene.

        Returns:
            List of scene dicts enriched with word_count, estimated_duration_sec
        """
        logger.info(f"Building scripts for {len(story['scenes'])} scenes")
        scripts = []

        for scene in story["scenes"]:
            narration = scene.get("narration", "").strip()
            word_count = len(narration.split())
            estimated_duration = max(3, round(word_count / 2.17))

            script = {
                "scene_number": scene["scene_number"],
                "title": scene.get("title", f"Scene {scene['scene_number']}"),
                "narration": narration,
                "visual_description": scene.get("visual_description", ""),
                "emotion": scene.get("emotion", "neutral"),
                "word_count": word_count,
                "estimated_duration_sec": estimated_duration,
                "duration_hint_sec": scene.get("duration_hint_sec", estimated_duration),
            }
            scripts.append(script)
            logger.debug(
                f"Scene {script['scene_number']}: {word_count} words "
                f"≈ {estimated_duration}s"
            )

        save_json({"story_title": story["title"], "scripts": scripts},
                  workspace / "scripts.json")

        total_duration = sum(s["estimated_duration_sec"] for s in scripts)
        logger.info(f"Total estimated duration: {total_duration}s "
                    f"({total_duration//60}m {total_duration%60}s)")

        return scripts

    def build_full_narration(self, scripts: list[dict]) -> str:
        """Concatenate all scene narrations into a single text."""
        return "\n\n".join(s["narration"] for s in scripts)

    def build_image_prompts(self, story: dict, scripts: list[dict]) -> list[str]:
        """Build image prompts always in English for AI image generation compatibility."""
        from config.settings import IMAGE_STYLE_SUFFIX, ANTHROPIC_API_KEY, CLAUDE_MODEL
        import anthropic

        language = story.get("language", "english")
        prompts = []

        # If non-English, translate visual descriptions to English first
        if language != "english":
            logger.info("Translating visual descriptions to English for image generation...")
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            scene_descriptions = "\n".join(
                f"Scene {s['scene_number']}: {s.get('visual_description', '')}"
                for s in scripts
            )

            translation_prompt = (
                f"Translate these scene descriptions to English for image generation.\n"
                f"Return ONLY a JSON array of strings, one per scene, in order.\n"
                f"No explanation, no markdown, no extra text.\n\n"
                f"Scenes to translate:\n{scene_descriptions}"
            )

            try:
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1000,
                    messages=[{"role": "user", "content": translation_prompt}],
                )
                raw = response.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                translated = json.loads(raw.strip())

                # Emotion/mood translation map for common values
                emotion_map = {
                    "బాధ": "sad", "సంతోషం": "happy", "భయం": "fearful",
                    "ఆశ్చర్యం": "surprised", "కోపం": "angry", "శాంతి": "peaceful",
                    "దుఃఖం": "sorrowful", "ధైర్యం": "courageous", "ప్రేమ": "loving",
                    "उदासी": "sad", "खुशी": "happy", "डर": "fearful",
                    "शांति": "peaceful", "क्रोध": "angry", "प्यार": "loving",
                }

                for i, script in enumerate(scripts):
                    desc = translated[i] if i < len(translated) else "A warm storybook scene"
                    raw_emotion = script.get("emotion", "peaceful")
                    # Translate emotion if it's non-English
                    emotion = emotion_map.get(raw_emotion, raw_emotion)
                    # If still non-ASCII, default to peaceful
                    if not emotion.isascii():
                        emotion = "peaceful"
                    prompt = (
                        f"{desc}. "
                        f"Mood: {emotion}. "
                        f"{IMAGE_STYLE_SUFFIX}"
                    )
                    prompts.append(prompt[:400])

                logger.info(f"Built {len(prompts)} translated image prompts")
                return prompts

            except Exception as e:
                logger.warning(f"Translation failed ({e}) — using fallback English prompts")

        # English story or fallback
        character_summary = "; ".join(
            f"{c['name']} ({c.get('description', '')})"
            for c in story.get("characters", [])
        )

        for script in scripts:
            prompt = (
                f"{script.get('visual_description', 'A warm storybook scene')}. "
                f"Characters: {character_summary}. "
                f"Mood: {script.get('emotion', 'peaceful')}. "
                f"Setting: {story.get('setting', '')}. "
                f"{IMAGE_STYLE_SUFFIX}"
            )
            prompts.append(prompt[:400])

        logger.info(f"Built {len(prompts)} image prompts")
        return prompts