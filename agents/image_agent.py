"""
agents/image_agent.py
Generates scene images via HuggingFace (free AI), Pollinations, Stability, or Picsum fallback.
"""

import os
import time
import struct
import zlib
import requests
from pathlib import Path

from config.settings import IMAGE_ENGINE, STABILITY_API_KEY, VIDEO_FORMATS
from utils.logger import get_logger

logger = get_logger("image_agent")

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
HF_MODEL = "black-forest-labs/FLUX.1-schnell"

SCENE_PALETTE = [
    (255, 223, 186), (186, 225, 255), (186, 255, 201),
    (255, 186, 255), (255, 255, 186), (186, 255, 255),
    (220, 190, 255), (255, 210, 190), (190, 255, 220),
    (255, 240, 190), (190, 220, 255), (255, 190, 220),
]


class ImageAgent:
    """Generates one image per scene for video background."""

    def generate_all(
        self,
        image_prompts: list[str],
        workspace: Path,
        format_type: str = "long",
    ) -> list[Path]:
        img_dir = workspace / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        image_files = []
        fmt = VIDEO_FORMATS[format_type]
        video_seed = int(time.time()) % 10000

        logger.info(
            f"Generating {len(image_prompts)} images | "
            f"engine={IMAGE_ENGINE} | seed={video_seed}"
        )

        for i, prompt in enumerate(image_prompts, start=1):
            out_path = img_dir / f"scene_{i:02d}.png"
            logger.info(f"Generating image {i}/{len(image_prompts)}")
            success = False

            # ── Primary engine ────────────────────────────────────────────────
            if IMAGE_ENGINE == "huggingface" and HUGGINGFACE_API_KEY:
                success = self._try_huggingface(prompt, out_path)

            elif IMAGE_ENGINE == "pollinations":
                success = self._try_pollinations(
                    prompt, out_path, fmt["width"], fmt["height"], i
                )

            elif IMAGE_ENGINE == "stability" and STABILITY_API_KEY:
                try:
                    self._stability_image(
                        prompt, out_path, fmt["width"], fmt["height"]
                    )
                    success = True
                except Exception as e:
                    logger.warning(f"Stability failed: {e}")

            # ── Fallback: Picsum → placeholder ────────────────────────────────
            if not success:
                try:
                    self._picsum_image(
                        out_path, fmt["width"], fmt["height"], i, video_seed
                    )
                    success = True
                    logger.info(f"Picsum fallback used for scene {i}")
                except Exception as e:
                    logger.warning(f"Picsum failed: {e}")

            if not success:
                self._placeholder_image(
                    out_path, fmt["width"], fmt["height"], i
                )
                logger.info(f"Placeholder used for scene {i}")

            image_files.append(out_path)

        return image_files

    def _try_huggingface(self, prompt: str, output_path: Path) -> bool:
        """
        Generate image using HuggingFace InferenceClient.
        Uses huggingface_hub library — handles routing automatically.
        """
        try:
            from huggingface_hub import InferenceClient

            clean = ''.join(c for c in prompt if ord(c) < 128).strip()
            if '.' in clean:
                clean = clean.split('.')[0]
            clean = clean[:200]

            if not clean:
                clean = "warm storybook scene with characters in nature"

            full_prompt = (
                f"{clean}, storybook illustration style, "
                f"colorful, warm lighting, children's book art, "
                f"detailed characters, family friendly"
            )

            logger.debug(f"HuggingFace prompt: {clean[:80]}...")

            client = InferenceClient(
                provider="hf-inference",
                api_key=HUGGINGFACE_API_KEY,
            )

            image = client.text_to_image(
                prompt=full_prompt,
                model=HF_MODEL,
                negative_prompt=(
                    "low quality, blurry, dark, scary, "
                    "violent, watermark, text"
                ),
            )

            image.save(str(output_path))
            size_kb = output_path.stat().st_size // 1024
            logger.info(
                f"HuggingFace saved: {output_path.name} ({size_kb}KB)"
            )
            time.sleep(1.5)
            return True

        except Exception as e:
            logger.warning(f"HuggingFace error: {e}")
            return False

    def _try_pollinations(
        self, prompt: str, output_path: Path,
        width: int, height: int, scene_num: int
    ) -> bool:
        """Try Pollinations as secondary AI image option."""
        from urllib.parse import quote

        clean = ''.join(c for c in prompt if ord(c) < 128).strip()
        if '.' in clean:
            clean = clean.split('.')[0]
        clean = clean[:120]

        if not clean:
            clean = "warm storybook scene with characters"

        full_prompt = (
            f"{clean}, storybook illustration, "
            f"colorful, children book art, warm lighting"
        )
        seed = (scene_num * 31 + int(time.time())) % 9999
        url = (
            f"https://image.pollinations.ai/prompt/{quote(full_prompt)}"
            f"?width={min(width, 1024)}&height={min(height, 1024)}"
            f"&nologo=true&model=flux&seed={seed}"
        )

        try:
            logger.debug(f"Pollinations: {clean[:60]}...")
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 5000:
                output_path.write_bytes(resp.content)
                logger.info(
                    f"Pollinations saved: {output_path.name} "
                    f"({len(resp.content)//1024}KB)"
                )
                time.sleep(2.0)
                return True
            else:
                logger.warning(f"Pollinations returned {resp.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Pollinations error: {e}")
            return False

    def _picsum_image(
        self, output_path: Path, width: int,
        height: int, scene_num: int, video_seed: int = 0
    ) -> None:
        """Random beautiful photo — unique seed per video so never repeats."""
        seed = (scene_num * 137 + video_seed) % 1000
        url = (
            f"https://picsum.photos/seed/{seed}"
            f"/{min(width, 1024)}/{min(height, 1024)}"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
        logger.info(f"Picsum saved: {output_path.name} (seed={seed})")
        time.sleep(0.5)

    def _stability_image(
        self, prompt: str, output_path: Path, width: int, height: int
    ) -> None:
        """Generate image using Stability AI (paid)."""
        import base64
        url = (
            "https://api.stability.ai/v1/generation/"
            "stable-diffusion-xl-1024-v1-0/text-to-image"
        )
        headers = {
            "Authorization": f"Bearer {STABILITY_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 7,
            "height": min(height, 1024),
            "width": min(width, 1024),
            "samples": 1,
            "steps": 30,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        output_path.write_bytes(
            base64.b64decode(resp.json()["artifacts"][0]["base64"])
        )
        time.sleep(1.0)

    def _placeholder_image(
        self, output_path: Path, width: int, height: int, scene_num: int
    ) -> None:
        """Solid color PNG — last resort fallback."""
        color = SCENE_PALETTE[(scene_num - 1) % len(SCENE_PALETTE)]
        output_path.write_bytes(self._make_png(width, height, color))
        logger.debug(f"Placeholder: {output_path.name}")

    def _make_png(self, width: int, height: int, rgb: tuple) -> bytes:
        def chunk(name, data):
            c = name + data
            return (
                struct.pack(">I", len(data)) + c +
                struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            )
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        row = b"\x00" + bytes(rgb) * width
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * height, 9))
            + chunk(b"IEND", b"")
        )