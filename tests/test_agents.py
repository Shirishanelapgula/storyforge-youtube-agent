"""
tests/test_agents.py
Unit tests for all agents — mocked to avoid real API calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Story Agent ────────────────────────────────────────────────────────────────

MOCK_STORY = {
    "title": "The Weaver and the Wind",
    "moral": "True generosity comes from the heart, not the hand.",
    "setting": "A small village on the edge of an enchanted forest",
    "theme": "kindness to strangers",
    "format_type": "long",
    "characters": [
        {
            "name": "Elara",
            "role": "hero",
            "description": "A young weaver with silver-streaked hair and warm brown eyes.",
            "voice_trait": "gentle and thoughtful",
        }
    ],
    "scenes": [
        {
            "scene_number": 1,
            "title": "The Empty Loom",
            "narration": "In a village wrapped in golden mist, a young weaver named Elara sat before her loom.",
            "visual_description": "Wide shot of a cozy workshop at dawn, loom centered, warm light.",
            "emotion": "peaceful",
            "duration_hint_sec": 10,
        },
        {
            "scene_number": 2,
            "title": "The Stranger Arrives",
            "narration": "A tired traveler knocked on her door, shivering in the cold wind.",
            "visual_description": "Close-up of a cloaked figure at a wooden door, snow falling.",
            "emotion": "curious",
            "duration_hint_sec": 10,
        },
    ],
    "call_to_action": "Subscribe for a new story every week!",
    "tags": ["moral story", "kindness", "animated fable", "children stories", "life lessons"],
    "description": "A heartwarming fable about a weaver who discovers the true meaning of generosity.",
}

MOCK_QUALITY = {"approved": True, "score": 0.93, "issues": [], "notes": "Clean content."}


class TestStoryAgent:
    @patch("agents.story_agent.anthropic.Anthropic")
    def test_generate_story_returns_valid_dict(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(MOCK_STORY))]
        )

        from agents.story_agent import StoryAgent
        agent = StoryAgent()
        story = agent.generate_story("long", "kindness to strangers")

        assert story["title"] == "The Weaver and the Wind"
        assert len(story["scenes"]) == 2
        assert story["format_type"] == "long"

    @patch("agents.story_agent.anthropic.Anthropic")
    def test_quality_check_returns_approval(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(MOCK_QUALITY))]
        )

        from agents.story_agent import StoryAgent
        agent = StoryAgent()
        result = agent.quality_check(MOCK_STORY)

        assert result["approved"] is True
        assert result["score"] >= 0.9

    @patch("agents.story_agent.anthropic.Anthropic")
    def test_banned_keyword_raises(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        bad_story = {**MOCK_STORY, "title": "violence and blood in the forest"}
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(bad_story))]
        )

        from agents.story_agent import StoryAgent
        agent = StoryAgent()
        with pytest.raises((ValueError, Exception)):
            agent.generate_story("long")


# ── Script Agent ───────────────────────────────────────────────────────────────

class TestScriptAgent:
    def test_build_scripts_returns_correct_count(self, tmp_path):
        from agents.script_agent import ScriptAgent
        agent = ScriptAgent()
        scripts = agent.build_scripts(MOCK_STORY, tmp_path)
        assert len(scripts) == 2

    def test_scripts_have_duration_estimate(self, tmp_path):
        from agents.script_agent import ScriptAgent
        agent = ScriptAgent()
        scripts = agent.build_scripts(MOCK_STORY, tmp_path)
        for s in scripts:
            assert s["estimated_duration_sec"] > 0

    def test_image_prompts_count_matches_scenes(self, tmp_path):
        from agents.script_agent import ScriptAgent
        agent = ScriptAgent()
        scripts = agent.build_scripts(MOCK_STORY, tmp_path)
        prompts = agent.build_image_prompts(MOCK_STORY, scripts)
        assert len(prompts) == len(scripts)


# ── Subtitle Agent ─────────────────────────────────────────────────────────────

class TestSubtitleAgent:
    def test_generates_srt_file(self, tmp_path):
        from agents.subtitle_agent import SubtitleAgent
        from agents.script_agent import ScriptAgent

        scripts = ScriptAgent().build_scripts(MOCK_STORY, tmp_path)
        durations = [10.0, 10.0]

        agent = SubtitleAgent()
        result = agent.generate(scripts, durations, tmp_path)

        assert result["srt"].exists()
        assert result["ass"].exists()
        content = result["srt"].read_text()
        assert "-->" in content

    def test_subtitle_block_count(self, tmp_path):
        from agents.subtitle_agent import SubtitleAgent
        from agents.script_agent import ScriptAgent

        scripts = ScriptAgent().build_scripts(MOCK_STORY, tmp_path)
        durations = [10.0, 10.0]

        agent = SubtitleAgent()
        result = agent.generate(scripts, durations, tmp_path)
        lines = result["srt"].read_text().strip().split("\n")
        # Should have multiple numbered blocks
        numbered = [l for l in lines if l.strip().isdigit()]
        assert len(numbered) >= 2


# ── Image Agent ────────────────────────────────────────────────────────────────

class TestImageAgent:
    def test_placeholder_images_created(self, tmp_path):
        from agents.image_agent import ImageAgent
        prompts = ["A forest scene", "A village at dawn"]
        agent = ImageAgent()
        images = agent.generate_all(prompts, tmp_path, "long")

        assert len(images) == 2
        for img in images:
            assert img.exists()
            assert img.suffix == ".png"
            assert img.stat().st_size > 0

    def test_png_is_valid(self, tmp_path):
        from agents.image_agent import ImageAgent
        agent = ImageAgent()
        images = agent.generate_all(["test scene"], tmp_path, "long")
        png_bytes = images[0].read_bytes()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# ── Output Manager ─────────────────────────────────────────────────────────────

class TestOutputManager:
    def test_high_score_routes_to_upload(self, tmp_path, monkeypatch):
        from core.output_manager import OutputManager
        import config.settings as settings

        monkeypatch.setattr(settings, "REVIEW_DIR", tmp_path / "review")
        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "upload")
        monkeypatch.setattr(settings, "AUTO_APPROVE_THRESHOLD", 0.85)

        # Create dummy video file
        video = tmp_path / "test_story_long.mp4"
        video.write_bytes(b"FAKE_VIDEO_DATA")

        manager = OutputManager()
        _, label = manager.route(
            video, MOCK_STORY, MOCK_QUALITY, "test_job_001"
        )
        assert label == "ready_to_upload"

    def test_low_score_routes_to_review(self, tmp_path, monkeypatch):
        from core.output_manager import OutputManager
        import config.settings as settings

        monkeypatch.setattr(settings, "REVIEW_DIR", tmp_path / "review")
        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "upload")
        monkeypatch.setattr(settings, "AUTO_APPROVE_THRESHOLD", 0.85)

        video = tmp_path / "test_story_long.mp4"
        video.write_bytes(b"FAKE_VIDEO_DATA")

        low_quality = {"approved": True, "score": 0.60, "issues": [], "notes": "Borderline"}
        manager = OutputManager()
        _, label = manager.route(video, MOCK_STORY, low_quality, "test_job_002")
        assert label == "review"


# ── Utils ──────────────────────────────────────────────────────────────────────

class TestRetry:
    def test_retry_succeeds_after_failures(self):
        from utils.retry import retry

        call_count = {"n": 0}

        @retry(max_attempts=3, delay=0.01)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("Not yet")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert call_count["n"] == 3

    def test_retry_raises_after_max_attempts(self):
        from utils.retry import retry

        @retry(max_attempts=2, delay=0.01)
        def always_fails():
            raise RuntimeError("Always fails")

        with pytest.raises(RuntimeError):
            always_fails()


class TestFileUtils:
    def test_sanitize_filename(self):
        from utils.file_utils import sanitize_filename
        result = sanitize_filename("Hello World! #1")
        assert "Hello" in result
        assert "World" in result
        assert " " not in result
        assert "!" not in result
        assert "#" not in result

    def test_unique_job_id_different_each_time(self):
        from utils.file_utils import unique_job_id
        a = unique_job_id("test")
        b = unique_job_id("test")
        # Timestamps differ so IDs should differ
        assert isinstance(a, str) and len(a) == 10
