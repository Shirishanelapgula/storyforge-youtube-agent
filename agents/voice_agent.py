"""
agents/voice_agent.py
Generates AI voice narration for each scene.
- English → ElevenLabs (premium) or gTTS
- Telugu/Hindi → always gTTS (ElevenLabs doesn't support these)
"""

import time
from pathlib import Path

from config.settings import (
    TTS_ENGINE,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
)
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("voice_agent")

# Languages ElevenLabs supports
ELEVENLABS_SUPPORTED = {"english"}

# gTTS language codes
GTTS_LANG_MAP = {
    "english": "en",
    "hindi":   "hi",
    "telugu":  "te",
}


class VoiceAgent:
    """Converts narration text into audio files per scene."""

    def generate_all(
        self,
        scripts: list[dict],
        workspace: Path,
        language: str = "english",
    ) -> list[Path]:
        """
        Generate audio for all scenes.
        Automatically picks correct TTS engine based on language.
        """
        audio_dir = workspace / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_files = []

        # Decide engine once for all scenes
        use_elevenlabs = (
            TTS_ENGINE == "elevenlabs"
            and ELEVENLABS_API_KEY
            and language in ELEVENLABS_SUPPORTED
        )

        engine_name = "ElevenLabs" if use_elevenlabs else f"gTTS ({language})"
        logger.info(
            f"Voice engine: {engine_name} | "
            f"language={language} | "
            f"scenes={len(scripts)}"
        )

        for script in scripts:
            scene_num = script["scene_number"]
            text = script["narration"]
            out_path = audio_dir / f"scene_{scene_num:02d}.mp3"

            logger.info(f"Generating voice scene {scene_num}/{len(scripts)}")

            if use_elevenlabs:
                self._elevenlabs_tts(text, out_path)
            else:
                self._gtts_tts(text, out_path, language)

            audio_files.append(out_path)
            logger.debug(f"Audio saved: {out_path.name}")

        return audio_files

    @retry(max_attempts=3, delay=3.0)
    def _elevenlabs_tts(self, text: str, output_path: Path) -> None:
        """Generate high-quality TTS using ElevenLabs — English only."""
        import requests

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.35,
                "similarity_boost": 0.85,
                "style": 0.60,
                "use_speaker_boost": True,
            },
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=60)

        if resp.status_code == 401:
            raise RuntimeError("ElevenLabs API key invalid")
        if resp.status_code == 429:
            raise RuntimeError("ElevenLabs rate limit — retrying")

        resp.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(resp.content)

        logger.debug(f"ElevenLabs: {len(resp.content)//1024}KB")
        time.sleep(0.5)

    @retry(max_attempts=3, delay=3.0)
    def _gtts_tts(
        self, text: str, output_path: Path, language: str = "english"
    ) -> None:
        """Generate TTS using Google — supports Telugu, Hindi, English."""
        from gtts import gTTS

        lang_code = GTTS_LANG_MAP.get(language, "en")
        logger.debug(f"gTTS: lang_code={lang_code}")
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.save(str(output_path))
        time.sleep(0.3)

    def get_audio_duration(self, audio_path: Path) -> float:
        """Return audio duration in seconds."""
        try:
            from mutagen.mp3 import MP3
            return MP3(str(audio_path)).info.length
        except Exception:
            return max(3.0, audio_path.stat().st_size / 1024 / 16)