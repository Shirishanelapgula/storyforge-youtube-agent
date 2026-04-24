"""
agents/wavespeed_agent.py
Generates cinematic video clips using WAN 2.6 via WaveSpeedAI.
Docs: https://wavespeed.ai/docs
Pricing: ~$0.10 per 5s clip
"""

import os
import time
import requests
from pathlib import Path

from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("wavespeed_agent")

WAVESPEED_API_KEY = os.getenv("WAVESPEED_API_KEY", "")

# Size presets per aspect ratio
SIZES = {
    "9:16": {
        "fast": "720*1280",
        "best": "1080*1920",
    },
    "16:9": {
        "fast": "1280*720",
        "best": "1920*1080",
    },
}


class WaveSpeedAgent:
    """Generates cinematic video clips using WAN 2.6 via WaveSpeedAI."""

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {WAVESPEED_API_KEY}",
            "Content-Type": "application/json",
        }
        self.base_url = "https://api.wavespeed.ai/api/v3"

    def generate_all(
        self,
        image_prompts: list[str],
        audio_files: list[Path],
        audio_durations: list[float],
        workspace: Path,
        format_type: str = "long",
    ) -> list[Path]:
        """Generate one video clip per scene."""
        video_dir = workspace / "wavespeed_clips"
        video_dir.mkdir(parents=True, exist_ok=True)

        aspect_ratio = "9:16" if format_type == "shorts" else "16:9"
        video_files = []

        for i, (prompt, audio_path, duration) in enumerate(
            zip(image_prompts, audio_files, audio_durations), start=1
        ):
            out_path = video_dir / f"scene_{i:02d}.mp4"
            logger.info(
                f"Generating WaveSpeed clip {i}/{len(image_prompts)} | "
                f"ratio={aspect_ratio}"
            )

            try:
                self._generate_clip(prompt, out_path, aspect_ratio)
                logger.info(f"WaveSpeed clip saved: {out_path.name}")
            except Exception as e:
                logger.warning(
                    f"WaveSpeed failed scene {i}: {e} — using fallback"
                )
                self._fallback_clip(audio_path, duration, out_path, aspect_ratio)

            video_files.append(out_path)

        return video_files

    @retry(max_attempts=2, delay=10.0)
    def _generate_clip(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str,
    ) -> None:
        """Submit → poll → download one WaveSpeed clip."""

        # Clean prompt — ASCII only, max 300 chars
        clean = ''.join(c for c in prompt if ord(c) < 128).strip()[:300]
        if not clean:
            clean = "A warm cinematic storybook scene with characters in nature"

        cinematic_prompt = (
            f"{clean}, "
            f"cinematic quality, smooth camera motion, "
            f"warm natural lighting, storybook animation style, "
            f"family friendly, vibrant colors"
        )

        size = SIZES.get(aspect_ratio, SIZES["16:9"])["fast"]

        payload = {
            "prompt": cinematic_prompt,
            "negative_prompt": (
                "low quality, blurry, distorted, watermark, "
                "text overlay, scary, violent, adult content"
            ),
            "size": size,
            "duration": 5,
            "shot_type": "single",
            "enable_prompt_expansion": True,
            "seed": -1,
        }

        logger.debug(f"WaveSpeed submit: {clean[:80]}...")
        logger.debug(f"Size={size} duration=5s aspect={aspect_ratio}")

        # ── Submit job ────────────────────────────────────────────────────────
        resp = requests.post(
            f"{self.base_url}/alibaba/wan-2.6/text-to-video",
            headers=self.headers,
            json=payload,
            timeout=30,
        )

        if resp.status_code == 402:
            raise RuntimeError(
                "WaveSpeed insufficient credits — top up at wavespeed.ai/billing"
            )
        if resp.status_code == 401:
            raise RuntimeError(
                "WaveSpeed invalid API key — check WAVESPEED_API_KEY in .env"
            )
        if resp.status_code == 400:
            logger.error(f"WaveSpeed 400 error: {resp.text}")
            raise RuntimeError(f"WaveSpeed bad request: {resp.text[:300]}")

        resp.raise_for_status()
        data = resp.json()
        logger.debug(f"Submit response: {data}")

        request_id = (
            data.get("data", {}).get("id") or
            data.get("id") or
            data.get("request_id")
        )

        if not request_id:
            raise RuntimeError(f"No request_id in response: {data}")

        logger.info(f"WaveSpeed job submitted: {request_id}")

        # ── Poll until done ───────────────────────────────────────────────────
        video_url = self._poll(request_id)

        # ── Download ──────────────────────────────────────────────────────────
        self._download(video_url, output_path)

    def _poll(self, request_id: str, timeout: int = 300) -> str:
        """Poll until video is ready. Returns download URL."""
        logger.info(f"Polling WaveSpeed job: {request_id}")

        # Initial wait — WAN 2.6 takes ~30-60 seconds
        time.sleep(20)

        for attempt in range(30):
            try:
                resp = requests.get(
                    f"{self.base_url}/predictions/{request_id}/result",
                    headers=self.headers,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"Poll attempt {attempt+1} failed: {e}")
                time.sleep(10)
                continue

            status = (
                data.get("data", {}).get("status") or
                data.get("status") or
                "processing"
            ).lower()

            outputs = (
                data.get("data", {}).get("outputs") or
                data.get("outputs") or
                []
            )

            logger.debug(f"Poll #{attempt+1}: status={status}")

            if status in ("completed", "succeeded", "success"):
                if outputs:
                    video_url = outputs[0] if isinstance(outputs, list) else outputs
                    return str(video_url)
                # Sometimes URL is nested differently
                video_url = (
                    data.get("data", {}).get("video_url") or
                    data.get("video_url")
                )
                if video_url:
                    return str(video_url)
                raise RuntimeError(
                    f"Status=completed but no video URL found in: {data}"
                )

            if status in ("failed", "error", "cancelled"):
                error = (
                    data.get("data", {}).get("error") or
                    data.get("error") or
                    status
                )
                raise RuntimeError(f"WaveSpeed job failed: {error}")

            wait = min(8 + attempt * 2, 20)
            logger.info(f"Processing... poll #{attempt+1} | waiting {wait}s")
            time.sleep(wait)

        raise RuntimeError(f"WaveSpeed timed out after {timeout}s")

    def _download(self, video_url: str, output_path: Path) -> None:
        """Download video to disk."""
        logger.info(f"Downloading: {video_url[:60]}...")
        resp = requests.get(
            video_url,
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()

        total = 0
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)

        logger.info(f"Saved: {output_path.name} ({total//1024}KB)")

    def _fallback_clip(
        self,
        audio_path: Path,
        duration: float,
        output_path: Path,
        aspect_ratio: str,
    ) -> None:
        """FFmpeg fallback using Picsum photo + audio — always has voice."""
        import subprocess
        import struct
        import zlib

        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
        safe_dur = max(3.0, float(duration))

        # Try Picsum photo first for better visuals
        import requests as req
        import time
        img_path = output_path.parent / f"{output_path.stem}_bg.jpg"
        try:
            seed = int(time.time()) % 1000
            r = req.get(
                f"https://picsum.photos/seed/{seed}/{w}/{h}",
                timeout=15
            )
            if r.status_code == 200:
                img_path.write_bytes(r.content)
                logger.info(f"Fallback using Picsum photo")
            else:
                raise Exception("Picsum failed")
        except Exception:
            # Pure color PNG fallback
            def make_png(width, height, rgb):
                def chunk(name, data):
                    c = name + data
                    return (
                        struct.pack(">I", len(data)) + c +
                        struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
                    )
                ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
                row = b"\x00" + bytes(rgb) * width
                return (
                    b"\x89PNG\r\n\x1a\n" +
                    chunk(b"IHDR", ihdr) +
                    chunk(b"IDAT", zlib.compress(row * height)) +
                    chunk(b"IEND", b"")
                )
            img_path = output_path.parent / f"{output_path.stem}_bg.png"
            img_path.write_bytes(make_png(min(w, 256), min(h, 256), (30, 60, 120)))
            logger.info(f"Fallback using colored PNG")

        # Render with AUDIO properly merged
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(safe_dur),
            "-i", str(img_path),         # Image input
            "-i", str(audio_path),       # Audio input ← MUST be present
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",               # Encode audio
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "1",
            "-pix_fmt", "yuv420p",
            "-vf", (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
            ),
            "-t", str(safe_dur),
            "-r", "30",
            "-movflags", "+faststart",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Fallback FFmpeg failed: {result.stderr[-500:]}")
        else:
            logger.info(f"Fallback clip with audio: {output_path.name}")

        # Cleanup
        if img_path.exists():
            img_path.unlink()