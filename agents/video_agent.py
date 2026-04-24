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
            # Use ffprobe for exact duration
            exact_dur = _get_duration(aud)
            if exact_dur <= 0:
                exact_dur = max(3.0, float(dur))
            else:
                exact_dur = max(3.0, exact_dur)
            self._render_scene_clip(img, aud, exact_dur, clip_path, w, h, fps)
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
        audio_files: list[Path] = None,
    ) -> Path:
        """
        Assemble final video from pre-rendered clips (WaveSpeed/Seedance/Veo).
        Merges narration audio since AI video clips have no audio.
        """
        from utils.file_utils import sanitize_filename

        # Step 1: Concatenate all scene clips
        concat_path = workspace / "concat_clips.mp4"
        self._concat_clips(scene_video_files, concat_path)

        # Step 2: Merge narration audio (AI clips have no audio)
        if audio_files:
            with_audio_path = workspace / "concat_with_audio.mp4"
            concat_path = self.merge_audio_with_video(
                concat_path, audio_files, with_audio_path
            )

        # Step 3: Burn subtitles
        safe_title = sanitize_filename(story["title"])
        final_path = workspace / f"{safe_title}_{format_type}.mp4"

        ass_path = subtitle_paths.get("ass")
        if ass_path and ass_path.exists():
            self._burn_subtitles(concat_path, ass_path, final_path)
        else:
            shutil.copy2(str(concat_path), str(final_path))

        logger.info(f"✅ Video rendered: {final_path}")
        return final_path

    def merge_audio_with_video(
        self,
        video_path: Path,
        audio_files: list[Path],
        output_path: Path,
    ) -> Path:
        """
        Merge narration audio tracks with a video that has no audio.
        Concatenates all scene audio files then merges with video.
        """
        # Step 1: Concatenate all audio files with re-encode for correct duration metadata
        audio_list = video_path.parent / "audio_list.txt"
        with open(audio_list, "w") as f:
            for audio in audio_files:
                f.write(f"file '{audio.resolve()}'\n")

        merged_audio = video_path.parent / "merged_narration.mp3"
        cmd_audio = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(audio_list),
            "-c:a", "libmp3lame",   # re-encode for correct duration metadata
            "-q:a", "2",
            str(merged_audio),
        ]
        result = subprocess.run(cmd_audio, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Audio concat failed: {result.stderr[-500:]}")
            return video_path

        # Step 2: Check durations and pad audio if shorter than video
        video_dur = _get_duration(video_path)
        audio_dur = _get_duration(merged_audio)
        gap = video_dur - audio_dur

        logger.info(f"Video dur: {video_dur:.2f}s | Audio dur: {audio_dur:.2f}s | Gap: {gap:.2f}s")

        if gap > 0.5:
            logger.info(f"Padding audio by {gap:.2f}s to match video")
            padded_audio = video_path.parent / "merged_narration_padded.mp3"
            pad_cmd = [
                "ffmpeg", "-y",
                "-i", str(merged_audio),
                "-af", f"apad=pad_dur={gap}",
                "-c:a", "libmp3lame",
                "-q:a", "2",
                str(padded_audio),
            ]
            result = subprocess.run(pad_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                merged_audio = padded_audio
            else:
                logger.warning("Audio padding failed — using unpadded audio")

        # Step 3: Merge audio with video — no -shortest so full video always plays
        cmd_merge = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(merged_audio),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "1",
            str(output_path),
        ]
        result = subprocess.run(cmd_merge, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Audio merge failed: {result.stderr[-500:]}")
            return video_path

        logger.info(f"Audio merged: {output_path.name}")
        return output_path

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
        safe_duration = max(3.0, float(duration))

        # Step 1: Convert image to safe PNG
        safe_img = output.parent / f"{output.stem}_safe.png"
        convert_cmd = [
            "ffmpeg", "-y",
            "-i", str(image),
            "-vf", (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"format=yuv420p"
            ),
            str(safe_img),
        ]
        subprocess.run(convert_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        input_img = (
            safe_img
            if safe_img.exists() and safe_img.stat().st_size > 0
            else image
        )

        # Step 2: Loop image slightly longer than audio, -shortest cuts on audio end
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(safe_duration + 1.0),
            "-i", str(input_img),
            "-i", str(audio),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "1",
            "-pix_fmt", "yuv420p",
            "-vf", (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1"
            ),
            "-shortest",
            "-r", str(fps),
            "-movflags", "+faststart",
            str(output),
        ]
        self._run_ffmpeg(cmd, f"scene clip {output.name}")

        if safe_img.exists():
            safe_img.unlink()

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

    def _burn_subtitles(self, video: Path, ass: Path, output: Path) -> None:
        """Burn subtitles — SRT on Windows, works on Linux too."""
        srt_path = ass.parent / "subtitles.srt"

        if srt_path.exists():
            srt_str = str(srt_path.resolve())

            # Windows path fix: C:/ → C\:/
            if len(srt_str) > 1 and srt_str[1] == ":":
                srt_safe = srt_str[0] + "\\:" + srt_str[2:].replace("\\", "/")
            else:
                srt_safe = srt_str.replace("\\", "/")

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
                logger.warning("Subtitle burn failed — copying without subtitles")

        shutil.copy2(str(video), str(output))
        logger.warning("Subtitles skipped — video copied without subtitles")

    def _run_ffmpeg(self, cmd: list, label: str) -> None:
        """Run an FFmpeg command, log output, raise on failure."""
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "FFmpeg not found. Install FFmpeg: https://ffmpeg.org/download.html"
            )

        logger.debug(f"FFmpeg [{label}]: {' '.join(cmd[:8])}...")
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