"""
agents/voice_agent.py
Generates AI voice narration for each scene.
- English → ElevenLabs (premium) or gTTS
- Telugu  → Sarvam AI (natural, expressive Indian Telugu voices)
- Hindi   → Sarvam AI (natural, expressive Indian Hindi voices)
"""

import os
import base64
import time
import requests
from pathlib import Path

from config.settings import (
    TTS_ENGINE,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
)
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("voice_agent")

# Sarvam AI config
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# Languages ElevenLabs supports
ELEVENLABS_SUPPORTED = {"english"}

# Languages Sarvam AI supports
SARVAM_SUPPORTED = {"telugu", "hindi"}

# Sarvam language codes
SARVAM_LANG_MAP = {
    "telugu": "te-IN",
    "hindi":  "hi-IN",
}

# Sarvam voice options per language
SARVAM_VOICE_MAP = {
    "telugu": "tanya",
    "hindi":  "tanya",
}

# gTTS language codes (fallback only)
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

        Telugu/Hindi → Sarvam AI (natural Indian voices)
        English      → ElevenLabs if key set, else gTTS
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
        use_sarvam = (
            language in SARVAM_SUPPORTED
            and SARVAM_API_KEY
        )

        if use_elevenlabs:
            engine_name = "ElevenLabs"
        elif use_sarvam:
            engine_name = f"Sarvam AI ({SARVAM_VOICE_MAP.get(language, 'tanya')})"
        else:
            engine_name = f"gTTS ({language})"
            if language in SARVAM_SUPPORTED and not SARVAM_API_KEY:
                logger.warning(
                    "SARVAM_API_KEY not set — falling back to gTTS. "
                    "Get a free key at https://sarvam.ai for much better Telugu/Hindi voices."
                )

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
            elif use_sarvam:
                self._sarvam_tts(text, out_path, language)
            else:
                self._gtts_tts(text, out_path, language)

            audio_files.append(out_path)
            logger.debug(f"Audio saved: {out_path.name}")

            # Pause between scenes to avoid Sarvam rate limits.
            # This only delays the API call — saved audio files are
            # unaffected so no gaps will appear in the final video.
            if use_sarvam and scene_num < len(scripts):
                time.sleep(5.0)

        return audio_files

    @retry(max_attempts=3, delay=30.0)
    def _sarvam_tts(
        self, text: str, output_path: Path, language: str = "telugu"
    ) -> None:
        import tempfile
        import subprocess
        import shutil

        lang_code = SARVAM_LANG_MAP.get(language, "te-IN")
        chunks = self._split_text(text, max_chars=490)
        temp_files = []

        try:
            for chunk in chunks:
                # Retry each chunk individually on rate limit
                for attempt in range(5):
                    resp = requests.post(
                        "https://api.sarvam.ai/text-to-speech",
                        headers={
                            "api-subscription-key": SARVAM_API_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "inputs": [chunk],
                            "target_language_code": lang_code,
                            "speaker": "tanya",
                            "model": "bulbul:v3",
                            "pace": 1.25,
                            "temperature": 0.95,
                            "enable_preprocessing": True,
                        },
                        timeout=30,
                    )

                    if resp.status_code == 429:
                        wait = 30 * (attempt + 1)  # 30s, 60s, 90s ...
                        logger.warning(
                            f"Sarvam rate limit — waiting {wait}s (attempt {attempt+1}/5)"
                        )
                        time.sleep(wait)
                        continue  # retry same chunk

                    if resp.status_code == 401:
                        raise RuntimeError(
                            "Sarvam API key invalid — check SARVAM_API_KEY"
                        )
                    if resp.status_code == 400:
                        logger.error(f"Sarvam 400 error body: {resp.text}")
                        raise RuntimeError(f"Sarvam bad request: {resp.text}")

                    resp.raise_for_status()

                    data = resp.json()
                    audio_b64 = data.get("audios", [None])[0]
                    if not audio_b64:
                        raise RuntimeError(f"No audio in Sarvam response: {data}")

                    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                    tmp.write(base64.b64decode(audio_b64))
                    tmp.close()
                    temp_files.append(tmp.name)
                    time.sleep(0.5)
                    break  # chunk succeeded — move to next
                else:
                    raise RuntimeError("Sarvam rate limit persists after 5 attempts")

            if len(temp_files) == 1:
                shutil.copy(temp_files[0], str(output_path))
            else:
                list_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False
                )
                for f in temp_files:
                    list_file.write(f"file '{f}'\n")
                list_file.close()

                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        list_file.name,
                        "-c:a",
                        "libmp3lame",
                        "-q:a",
                        "2",
                        str(output_path),
                    ],
                    check=True,
                    capture_output=True,
                )
                Path(list_file.name).unlink(missing_ok=True)

            logger.info(
                f"Sarvam TTS: {output_path.name} ({output_path.stat().st_size // 1024}KB)"
            )

        finally:
            for f in temp_files:
                Path(f).unlink(missing_ok=True)

    @retry(max_attempts=3, delay=3.0)
    def _elevenlabs_tts(self, text: str, output_path: Path) -> None:
        """Generate high-quality TTS using ElevenLabs — English only."""
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
        output_path.write_bytes(resp.content)

        logger.debug(f"ElevenLabs: {len(resp.content)//1024}KB")
        time.sleep(0.5)

    @retry(max_attempts=3, delay=3.0)
    def _gtts_tts(
        self, text: str, output_path: Path, language: str = "english"
    ) -> None:
        """Generate TTS using Google — fallback only."""
        from gtts import gTTS

        lang_code = GTTS_LANG_MAP.get(language, "en")
        logger.debug(f"gTTS: lang_code={lang_code} language={language}")

        tts = gTTS(
            text=text,
            lang=lang_code,
            slow=False,
            lang_check=False,
        )
        tts.save(str(output_path))
        time.sleep(0.3)

    def _split_text(self, text: str, max_chars: int = 490) -> list[str]:
        """
        Split long text into chunks at sentence boundaries.
        Sarvam API has a 500 char limit per request.
        """
        if len(text) <= max_chars:
            return [text]

        import re
        sentences = re.split(r'(?<=[.!?।\n])\s+', text.strip())

        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                # If single sentence is too long, hard split it
                if len(sentence) > max_chars:
                    for i in range(0, len(sentence), max_chars):
                        chunks.append(sentence[i:i+max_chars])
                else:
                    current = sentence

        if current:
            chunks.append(current)

        return chunks

    def get_audio_duration(self, audio_path: Path) -> float:
        """Return audio duration in seconds via ffprobe — more accurate than mutagen."""
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(audio_path)],
            capture_output=True, text=True,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return max(3.0, audio_path.stat().st_size / 1024 / 16)
