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
        """
        Build detailed ENGLISH visual prompts for each scene.
        These go to FLUX image generation — must be visual, not narration.
        """
        characters = story.get("characters", [])
        setting = story.get("setting", "Indian village")
        style = (
            "storybook illustration style, warm cinematic lighting, "
            "vibrant colors, family friendly, high quality digital art, "
            "detailed characters, emotionally engaging"
        )

        # Build character description string
        char_desc = ""
        if characters:
            names = [c.get("name", "") for c in characters[:2]]
            appearances = [c.get("appearance", "") for c in characters[:2]]
            char_desc = ". ".join(
                f"{n}: {a}" for n, a in zip(names, appearances) if n and a
            )

        prompts = []
        for script in scripts:
            scene_num = script.get("scene_number", 1)
            # Use visual_description if available, else build from narration
            visual = (
                script.get("visual_description") or
                script.get("scene_description") or
                script.get("setting") or
                ""
            )

            # Clean visual to ASCII only (FLUX needs English)
            visual_clean = ''.join(
                c for c in visual if ord(c) < 128
            ).strip()

            # If visual is empty or too short, use scene emotion + story context
            if len(visual_clean) < 20:
                emotion = script.get("emotion", "warm")
                action = script.get("action", "")
                action_clean = ''.join(
                    c for c in (action or "") if ord(c) < 128
                ).strip()

                visual_clean = (
                    f"Scene {scene_num}: {emotion} moment in {setting}. "
                    f"{action_clean}"
                ).strip()

            # Build final FLUX prompt
            prompt = (
                f"{visual_clean}"
                f"{'. ' + char_desc if char_desc else ''}. "
                f"{style}"
            )

            # Trim to 300 chars max for FLUX
            prompt = prompt[:300]
            prompts.append(prompt)

            logger.debug(f"Scene {scene_num} FLUX prompt: {prompt[:100]}...")

        logger.info(f"Built {len(prompts)} visual image prompts")
        return prompts