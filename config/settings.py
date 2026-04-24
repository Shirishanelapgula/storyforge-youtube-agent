"""
config/settings.py
Central configuration for the YouTube Content Creation Agent.
"""

import os
from pathlib import Path

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
REVIEW_DIR = OUTPUT_DIR / "review"
UPLOAD_DIR = OUTPUT_DIR / "ready_to_upload"
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"
WATCH_DIR = BASE_DIR / "inbox"          # Drop .json job files here to trigger

# ─── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")        # Optional
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY", "")          # Optional

# ─── Claude Model ─────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 6000
CLAUDE_MAX_TOKENS_LONG = 12000   # Long videos need more tokens

# ─── Video Formats ────────────────────────────────────────────────────────────
VIDEO_FORMATS = {
    "shorts": {
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "max_duration_sec": 59,
        "fps": 30,
        "target_scenes": 6,
    },
    "long": {
        "width": 1920,
        "height": 1080,
        "aspect": "16:9",
        "min_duration_sec": 300,   # 5 min
        "max_duration_sec": 600,   # 10 min
        "fps": 30,
        "target_scenes": 10,
    },
}

# ─── Voice Settings ───────────────────────────────────────────────────────────
TTS_ENGINE = os.getenv("TTS_ENGINE", "gtts")   # "gtts" | "elevenlabs" | "pyttsx3"
TTS_LANGUAGE = "en"
TTS_SLOW = False
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

# ─── Image Generation ─────────────────────────────────────────────────────────
IMAGE_ENGINE = os.getenv("IMAGE_ENGINE", "placeholder")  # "stability" | "placeholder"
IMAGE_STYLE_SUFFIX = (
    "digital art, warm tones, storybook illustration style, "
    "vibrant colors, cinematic lighting, family-friendly, 4K"
)

# ─── Subtitle Settings ────────────────────────────────────────────────────────
SUBTITLE_FONT = str(ASSETS_DIR / "fonts" / "Roboto-Bold.ttf")
SUBTITLE_FONT_SIZE = 48
SUBTITLE_COLOR = "white"
SUBTITLE_BORDER_COLOR = "black"
SUBTITLE_BORDER_WIDTH = 3
SUBTITLE_POSITION = "bottom"           # "bottom" | "center"
WORDS_PER_SUBTITLE_BLOCK = 6

# ─── Pipeline Settings ────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY_SEC = 5
AUTO_APPROVE_THRESHOLD = 0.85          # Quality score 0–1; above → ready_to_upload
SCENE_IMAGE_DURATION_SEC = 5          # Duration each scene image stays on screen

# ─── Story Themes ─────────────────────────────────────────────────────────────
MORAL_THEMES = [
    "honesty and integrity",
    "kindness to strangers",
    "perseverance through failure",
    "courage in adversity",
    "empathy and understanding",
    "gratitude and appreciation",
    "teamwork and cooperation",
    "humility and self-improvement",
    "protecting nature and animals",
    "forgiveness and second chances",
]

# ─── Monetization Guard ───────────────────────────────────────────────────────
BANNED_CONTENT_KEYWORDS = [
    "violence", "blood", "weapon", "drug", "sexual", "hate",
    "politics", "religion", "controversial", "gambling",
]

# ─── Language Settings ────────────────────────────────────────────────────────
SUPPORTED_LANGUAGES = {
    "english": {"code": "en", "gtts_lang": "en", "name": "English"},
    "hindi":   {"code": "hi", "gtts_lang": "hi", "name": "Hindi"},
    "telugu":  {"code": "te", "gtts_lang": "te", "name": "Telugu"},
}
CONTENT_LANGUAGE = os.getenv("CONTENT_LANGUAGE", "english")

# ─── Seedance Video Engine ─────────────────────────────────────────────────────
SEEDANCE_API_KEY = os.getenv("SEEDANCE_API_KEY", "")
SEEDANCE_BASE_URL = os.getenv("SEEDANCE_BASE_URL", "https://api.apimall.com/v1")
VIDEO_ENGINE = os.getenv("VIDEO_ENGINE", "ffmpeg")  # "ffmpeg" | "seedance"


# ─── Video Engines ────────────────────────────────────────────────────────────
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY", "")
WAVESPEED_API_KEY = os.getenv("WAVESPEED_API_KEY", "")