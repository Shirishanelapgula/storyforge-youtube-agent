"""
agents/video_agent.py
Assembles final video from scene images, audio, and subtitles using FFmpeg.
"""

import shutil
import subprocess
from pathlib import Path

from config.settings import VIDEO_FORMATS
from utils.logger import get_logger
from utils.retry import retry

logger = get_logger("video_agent")


class VideoAgent:
    """Renders final YouTube-ready video from all pipeline assets."""

    def render(
        self,
        image_files: list[Path],
        audio_files: list[Path],
        audio_durations: list[float],
        subtitle_paths: dict,
        workspace: Path,
        story: dict,
        format_type: str = "long",
    ) -> Path:
        fmt = VIDEO_FORMATS[format_type]
        w, h = fmt["width"], fmt["height"]
        fps = fmt["fps"]

        clips_dir = workspace / "clips"
        clips_dir.mkdir(exist_ok=True)

        scene_clips = []

        # Step 1: Per-scene video clips
        for i, (img, aud, dur) in enumerate(
            zip(image_files, audio_files, audio_durations), start=1
        ):
            clip_path = clips_dir / f"clip_{i:02d}.mp4"
            self._render_scene_clip(img, aud, dur, clip_path, w, h, fps)
            scene_clips.append(clip_path)

        # Step 2: Concatenate clips
        concat_path = workspace / "concat.mp4"
        self._concat_clips(scene_clips, concat_path)

        # Step 3: Burn subtitles
        from utils.file_utils import sanitize_filename
        safe_title = sanitize_filename(story["title"])
        final_path = workspace / f"{safe_title}_{format_type}.mp4"

        ass_path = subtitle_paths.get("ass")
        if ass_path and ass_path.exists():
            self._burn_subtitles(concat_path, ass_path, final_path)
        else:
            concat_path.rename(final_path)

        logger.info(f"✅ Video rendered: {final_path}")
        return final_path
    
    def render_from_clips(
        self,
        scene_video_files: list[Path],
        subtitle_paths: dict,
        workspace: Path,
        story: dict,
        format_type: str = "long",
    ) -> Path:
        """
        Assemble final video from pre-rendered Seedance clips.
        Seedance clips already have visuals — just concatenate + burn subtitles.
        """
        from utils.file_utils import sanitize_filename

        # Concatenate all Seedance clips
        concat_path = workspace / "concat_seedance.mp4"
        self._concat_clips(scene_video_files, concat_path)

        # Burn subtitles
        safe_title = sanitize_filename(story["title"])
        final_path = workspace / f"{safe_title}_{format_type}.mp4"

        ass_path = subtitle_paths.get("ass")
        if ass_path and ass_path.exists():
            self._burn_subtitles(concat_path, ass_path, final_path)
        else:
            concat_path.rename(final_path)

        logger.info(f"✅ Seedance video rendered: {final_path}")
        return final_path

    @retry(max_attempts=2, delay=3.0)
    def _render_scene_clip(
        self,
        image: Path,
        audio: Path,
        duration: float,
        output: Path,
        width: int,
        height: int,
        fps: int,
    ) -> None:
        """Create a video clip from one image + one audio file."""
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image),
            "-i", str(audio),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-t", str(duration),
            "-shortest",
            "-r", str(fps),
            str(output),
        ]
        self._run_ffmpeg(cmd, f"scene clip {output.name}")

    @retry(max_attempts=2, delay=3.0)
    def _concat_clips(self, clips: list[Path], output: Path) -> None:
        """Concatenate multiple .mp4 clips using FFmpeg concat demuxer."""
        list_file = output.parent / "concat_list.txt"
        with open(list_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip.resolve()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ]
        self._run_ffmpeg(cmd, "concatenation")

    def _burn_subtitles(
        self, video: Path, ass: Path, output: Path
    ) -> None:
        """Burn subtitles using SRT for Windows compatibility."""
        srt_path = ass.parent / "subtitles.srt"

        if srt_path.exists():
            srt_safe = str(srt_path.resolve()).replace("\\", "/")
            if len(srt_safe) > 1 and srt_safe[1] == ":":
                srt_safe = srt_safe[0] + "\\:" + srt_safe[2:]

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", (
                    f"subtitles='{srt_safe}':"
                    f"force_style='FontSize=24,"
                    f"PrimaryColour=&H00ffffff,"
                    f"OutlineColour=&H00000000,"
                    f"Outline=2,Bold=1,Alignment=2'"
                ),
                "-c:a", "copy",
                str(output),
            ]
            try:
                self._run_ffmpeg(cmd, "subtitle burn-in")
                return
            except RuntimeError:
                logger.warning("SRT subtitle burn failed — copying without subtitles")

        shutil.copy2(str(video), str(output))
        logger.warning("Subtitles skipped — video copied without subtitles")

    def _run_ffmpeg(self, cmd: list, label: str) -> None:
        """Run an FFmpeg command, log output, raise on failure."""
        logger.debug(f"FFmpeg [{label}]: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg [{label}] failed:\n{result.stderr[-2000:]}")
            raise RuntimeError(f"FFmpeg failed during {label}")
        logger.debug(f"FFmpeg [{label}] completed OK")