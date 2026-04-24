"""
agents/motion_agent.py
Two-step cinematic pipeline:
  Step 1: Generate story-relevant images using WaveSpeed FLUX (~$0.006/image)
  Step 2: Apply Ken Burns motion effect using FFmpeg (free)
"""

import os
import time
import subprocess
import requests
import random
from pathlib import Path

from config.settings import VIDEO_FORMATS
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("motion_agent")

WAVESPEED_API_KEY = os.getenv("WAVESPEED_API_KEY", "")
FLUX_MODEL = "wavespeed-ai/flux-dev"

# Ken Burns presets — scale to 2x output size (not 8000px which causes timeout)
MOTION_PRESETS = [
    {"name": "zoom_in",   "expr": "scale=iw*2:ih*2,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h},fps={fps}"},
    {"name": "zoom_out",  "expr": "scale=iw*2:ih*2,zoompan=z='if(lte(zoom,1.0),1.5,max(1.0,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h},fps={fps}"},
    {"name": "pan_right", "expr": "scale=iw*2:ih*2,zoompan=z='1.3':x='min(iw-(iw/zoom),on*3)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h},fps={fps}"},
    {"name": "pan_left",  "expr": "scale=iw*2:ih*2,zoompan=z='1.3':x='max(0,iw-(iw/zoom)-on*3)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h},fps={fps}"},
    {"name": "pan_up",    "expr": "scale=iw*2:ih*2,zoompan=z='1.3':x='iw/2-(iw/zoom/2)':y='max(0,ih-(ih/zoom)-on*3)':d={frames}:s={w}x{h},fps={fps}"},
    {"name": "zoom_pan",  "expr": "scale=iw*2:ih*2,zoompan=z='min(zoom+0.001,1.4)':x='iw/2-(iw/zoom/2)+on':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h},fps={fps}"},
]


def _get_duration(path: Path) -> float:
    """Get exact media duration via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


class MotionAgent:
    """FLUX images + Ken Burns motion — relevant characters at ~$0.04/video"""

    def __init__(self):
        import shutil
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg not found.")
        logger.info("MotionAgent ready — FLUX + Ken Burns")

    def generate_all(
        self,
        image_prompts: list[str],
        audio_files: list[Path],
        audio_durations: list[float],
        workspace: Path,
        format_type: str = "shorts",
    ) -> list[Path]:
        fmt = VIDEO_FORMATS[format_type]
        w, h = fmt["width"], fmt["height"]
        fps = fmt.get("fps", 30)

        img_dir = workspace / "flux_images"
        clips_dir = workspace / "motion_clips"
        img_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)

        presets = MOTION_PRESETS.copy()
        random.shuffle(presets)
        video_seed = int(time.time()) % 10000
        video_files = []

        logger.info(
            f"MotionAgent: {len(image_prompts)} scenes | "
            f"format={format_type} | {w}x{h}"
        )

        for i, (prompt, audio, duration) in enumerate(
            zip(image_prompts, audio_files, audio_durations), start=1
        ):
            img_path = img_dir / f"scene_{i:02d}.jpg"
            out_path = clips_dir / f"scene_{i:02d}.mp4"
            preset = presets[i % len(presets)]

            # Use ffprobe for exact audio duration — more accurate than mutagen
            exact_dur = _get_duration(audio)
            if exact_dur <= 0:
                exact_dur = max(3.0, float(duration))
            else:
                exact_dur = max(3.0, exact_dur)

            logger.info(f"Scene {i}/{len(image_prompts)} | effect={preset['name']} | dur={exact_dur:.2f}s")
            logger.debug(f"Prompt: {prompt[:100]}")

            # Step 1 — Generate relevant image via FLUX
            img_ok = False
            if WAVESPEED_API_KEY:
                img_ok = self._generate_flux_image(prompt, img_path, w, h, i)
            if not img_ok:
                self._picsum_fallback(img_path, w, h, i, video_seed)

            # Step 2 — Ken Burns motion + embed audio
            try:
                self._render_motion_clip(
                    img_path, audio, exact_dur, out_path, w, h, fps, preset
                )
                # Verify output duration matches audio
                out_dur = _get_duration(out_path)
                logger.info(f"Saved: {out_path.name} ({out_path.stat().st_size//1024}KB) | clip_dur={out_dur:.2f}s")
            except Exception as e:
                logger.warning(f"Ken Burns failed: {e} — static fallback")
                self._static_fallback(img_path, audio, exact_dur, out_path, w, h, fps)

            video_files.append(out_path)

        return video_files

    @retry(max_attempts=2, delay=5.0)
    def _generate_flux_image(
        self, prompt: str, output_path: Path,
        width: int, height: int, scene_num: int
    ) -> bool:
        clean = ''.join(c for c in prompt if ord(c) < 128).strip()[:250]
        if not clean:
            clean = "Warm cinematic storybook scene with Indian characters"

        full_prompt = (
            f"{clean}. Storybook illustration style, "
            f"warm cinematic lighting, vibrant colors, "
            f"family friendly, high quality digital art"
        )

        size = "720*1280" if height > width else "1280*720"

        headers = {
            "Authorization": f"Bearer {WAVESPEED_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": full_prompt,
            "size": size,
            "num_inference_steps": 20,
            "guidance_scale": 3.5,
            "seed": (scene_num * 137 + int(time.time())) % 99999,
            "output_format": "png",
        }

        resp = requests.post(
            f"https://api.wavespeed.ai/api/v3/{FLUX_MODEL}",
            headers=headers, json=payload, timeout=60,
        )

        if resp.status_code in (402, 400, 401, 403, 404):
            logger.warning(f"FLUX {resp.status_code}: {resp.text[:150]}")
            return False

        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("data", {}).get("id") or data.get("id")
        poll_url = (
            data.get("data", {}).get("urls", {}).get("get") or
            f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
        )

        if not task_id:
            return False

        logger.info(f"WaveSpeed task submitted: {task_id}")
        image_url = self._poll_image(poll_url, headers)

        if not image_url:
            return False

        img_resp = requests.get(image_url, timeout=30)
        img_resp.raise_for_status()
        output_path.write_bytes(img_resp.content)
        logger.info(f"FLUX image: {output_path.name} ({output_path.stat().st_size//1024}KB)")
        time.sleep(0.5)
        return True

    def _poll_image(self, poll_url: str, headers: dict, max_wait: int = 90) -> str:
        elapsed = 0
        interval = 3
        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval
            try:
                resp = requests.get(poll_url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                result = data.get("data", data)
                status = result.get("status", "")
                if status == "completed":
                    outputs = result.get("outputs", [])
                    if isinstance(outputs, list) and outputs:
                        return outputs[0]
                elif status == "failed":
                    return None
            except Exception:
                pass
        return None

    def _render_motion_clip(
        self,
        image: Path, audio: Path, duration: float,
        output: Path, width: int, height: int,
        fps: int, preset: dict,
    ) -> None:
        """Ken Burns effect — image loops for exact audio duration."""
        safe_dur = max(3.0, float(duration))
        frames = int(safe_dur * fps)

        vf = (
            preset["expr"]
            .replace("{frames}", str(frames))
            .replace("{w}", str(width))
            .replace("{h}", str(height))
            .replace("{fps}", str(fps))
        )
        vf += ",format=yuv420p"

        cmd = [
            "ffmpeg", "-y",
            # Loop image for slightly longer than audio so -shortest
            # always cuts on audio end, never on video end
            "-loop", "1",
            "-t", str(safe_dur + 1.0),
            "-i", str(image),
            "-i", str(audio),
            "-vf", vf,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "1",
            "-shortest",        # clip ends exactly when audio ends
            "-movflags", "+faststart",
            str(output),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"Ken Burns error: {result.stderr[-400:]}")
            raise RuntimeError("Ken Burns render failed")

    def _picsum_fallback(
        self, output_path: Path, width: int,
        height: int, scene_num: int, video_seed: int
    ) -> None:
        seed = (scene_num * 137 + video_seed) % 1000
        url = f"https://picsum.photos/seed/{seed}/{min(width,1024)}/{min(height,1024)}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            logger.info(f"Picsum fallback: scene_{scene_num:02d}")
        except Exception:
            self._color_placeholder(output_path, width, height, scene_num)

    def _color_placeholder(
        self, output_path: Path, width: int, height: int, scene_num: int
    ) -> None:
        import struct, zlib
        colors = [(255,223,186),(186,225,255),(186,255,201),(255,186,255),(255,255,186),(186,255,255)]
        rgb = colors[(scene_num - 1) % len(colors)]
        w, h = min(width, 256), min(height, 256)
        def chunk(name, data):
            c = name + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        row = b"\x00" + bytes(rgb) * w
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(row * h)) + chunk(b"IEND", b"")
        output_path.write_bytes(png)

    def _static_fallback(
        self, image: Path, audio: Path, duration: float,
        output: Path, width: int, height: int, fps: int,
    ) -> None:
        safe_dur = max(3.0, float(duration))
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(safe_dur + 1.0),
            "-i", str(image),
            "-i", str(audio),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "128k",
            "-ar", "44100", "-ac", "1",
            "-pix_fmt", "yuv420p",
            "-vf", (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"),
            "-shortest",
            "-r", str(fps),
            "-movflags", "+faststart",
            str(output),
        ]
        subprocess.run(cmd, capture_output=True)
        logger.info(f"Static fallback: {output.name}")