"""
agents/seedance_agent.py
Generates cinematic video clips using Seedance 2.0 via API Mall.
Docs: https://apimall.ai/docs/model-guides/video-models/seedance
"""

import time
import requests
from pathlib import Path

from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("seedance_agent")


class SeedanceAgent:
    """Generates one cinematic video clip per scene using Seedance 2.0."""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def generate_all(
        self,
        image_prompts: list[str],
        audio_files: list[Path],
        audio_durations: list[float],
        workspace: Path,
        format_type: str = "long",
    ) -> list[Path]:
        """Generate one Seedance video clip per scene."""
        video_dir = workspace / "seedance_clips"
        video_dir.mkdir(parents=True, exist_ok=True)

        aspect_ratio = "9:16" if format_type == "shorts" else "16:9"
        video_files = []

        for i, (prompt, audio_path, duration) in enumerate(
            zip(image_prompts, audio_files, audio_durations), start=1
        ):
            out_path = video_dir / f"scene_{i:02d}.mp4"
            logger.info(
                f"Generating Seedance clip {i}/{len(image_prompts)} "
                f"| duration={int(duration)}s | ratio={aspect_ratio}"
            )

            try:
                self._generate_clip(
                    prompt, out_path, aspect_ratio, duration
                )
            except Exception as e:
                logger.warning(
                    f"Seedance failed scene {i}: {e} — using fallback"
                )
                self._fallback_clip(audio_path, duration, out_path, aspect_ratio)

            video_files.append(out_path)

        return video_files

    @retry(max_attempts=2, delay=15.0)
    def _generate_clip(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str,
        duration: float,
    ) -> None:
        """Submit → poll → download one Seedance clip."""

        # ── Step 1: Submit generation task ───────────────────────────────────
        task_id = self._submit(prompt, aspect_ratio, duration)
        logger.info(f"Seedance task submitted: {task_id}")

        # ── Step 2: Poll until done ───────────────────────────────────────────
        video_url = self._poll(task_id)
        logger.info(f"Seedance task complete: {video_url[:60]}...")

        # ── Step 3: Download ──────────────────────────────────────────────────
        self._download(video_url, output_path)

    def _submit(
        self, prompt: str, aspect_ratio: str, duration: float
    ) -> str:
        """Submit video generation task. Returns task_id."""

        # Clean prompt — ASCII only, max 400 chars
        clean = ''.join(c for c in prompt if ord(c) < 128).strip()[:400]
        if not clean:
            clean = "A warm cinematic storybook scene with characters in nature"

        # Clamp duration to Seedance supported values (5 or 10)
        dur = 10 if duration > 7 else 5

        payload = {
            "model": "seedance",
            "type": "text-to-video",
            "prompt": clean,
            "aspect_ratio": aspect_ratio,
            "duration": str(dur),
            "resolution": "720p",
            "fixed_lens": False,
            "generate_audio": False,  # We use our own gTTS audio
        }

        logger.debug(f"Seedance submit payload: {payload}")

        resp = requests.post(
            f"{self.base_url}/videos/generate",
            headers=self.headers,
            json=payload,
            timeout=60,
        )

        if resp.status_code == 401:
            raise RuntimeError("Invalid API key — check SEEDANCE_API_KEY in .env")
        if resp.status_code == 402:
            raise RuntimeError("Insufficient API Mall credits — top up at apimall.ai")
        if resp.status_code == 429:
            raise RuntimeError("Rate limited — retrying")

        resp.raise_for_status()
        data = resp.json()
        logger.debug(f"Seedance submit response: {data}")

        if not data.get("success"):
            raise RuntimeError(f"Seedance submit failed: {data}")

        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")

        credits_used = data.get("data", {}).get("credits_used", "?")
        remaining = data.get("data", {}).get("remaining_credits", "?")
        logger.info(f"Credits used: {credits_used} | Remaining: {remaining}")

        return task_id

    def _poll(self, task_id: str, timeout: int = 300) -> str:
        """Poll status endpoint until video is ready. Returns video URL."""

        status_url = f"{self.base_url}/videos/status/{task_id}"
        logger.info(f"Polling Seedance task: {task_id}")

        # Initial wait — Seedance takes ~30-90 seconds
        time.sleep(20)

        for attempt in range(30):
            resp = requests.get(
                status_url,
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            status = (
                data.get("data", {}).get("status") or
                data.get("status") or
                "processing"
            ).lower()

            video_url = (
                data.get("data", {}).get("video_url") or
                data.get("data", {}).get("url") or
                data.get("video_url")
            )

            logger.debug(
                f"Poll #{attempt+1}: status={status} | "
                f"url={'found' if video_url else 'not yet'}"
            )

            if status in ("completed", "succeeded", "success", "done"):
                if video_url:
                    return video_url
                raise RuntimeError(
                    f"Status={status} but no video_url in: {data}"
                )

            if status in ("failed", "error", "cancelled"):
                error = (
                    data.get("data", {}).get("error") or
                    data.get("message") or
                    status
                )
                raise RuntimeError(f"Seedance task failed: {error}")

            # Still processing
            wait = min(10 + attempt * 2, 30)
            logger.info(
                f"Seedance processing... poll #{attempt+1} | "
                f"waiting {wait}s"
            )
            time.sleep(wait)

        raise RuntimeError(f"Seedance timed out after {timeout}s | task={task_id}")

    def _download(self, video_url: str, output_path: Path) -> None:
        """Download generated video to disk."""
        resp = requests.get(video_url, timeout=120, stream=True)
        resp.raise_for_status()

        total = 0
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)

        logger.info(
            f"Seedance video saved: {output_path.name} "
            f"({total//1024}KB)"
        )

    def _fallback_clip(
        self,
        audio_path: Path,
        duration: float,
        output_path: Path,
        aspect_ratio: str,
    ) -> None:
        """FFmpeg fallback if Seedance fails."""
        import subprocess, struct, zlib

        w, h = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)

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

        tmp = output_path.parent / f"{output_path.stem}_tmp.png"
        tmp.write_bytes(make_png(min(w, 256), min(h, 256), (30, 60, 120)))

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(tmp),
            "-i", str(audio_path),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-vf", (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-t", str(duration), "-shortest", "-r", "30",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True)
        tmp.unlink(missing_ok=True)
        logger.info(f"Fallback clip created: {output_path.name}")