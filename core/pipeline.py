"""
core/pipeline.py
Orchestrates the full content creation pipeline.
"""

from pathlib import Path

from agents.story_agent import StoryAgent
from agents.script_agent import ScriptAgent
from agents.voice_agent import VoiceAgent
from agents.image_agent import ImageAgent
from agents.subtitle_agent import SubtitleAgent
from agents.video_agent import VideoAgent
from core.job_manager import JobManager, JobStatus
from core.output_manager import OutputManager
from config.settings import (
    BASE_DIR,
    SEEDANCE_API_KEY,
    SEEDANCE_BASE_URL,
    VIDEO_ENGINE,
    GEMINI_API_KEY,
    REPLICATE_API_KEY,
    WAVESPEED_API_KEY,
)
from utils.logger import get_logger
from utils.file_utils import job_workspace, unique_job_id

logger = get_logger("pipeline")


class ContentPipeline:
    """End-to-end content creation pipeline."""

    def __init__(self):
        self.story_agent = StoryAgent()
        self.script_agent = ScriptAgent()
        self.voice_agent = VoiceAgent()
        self.image_agent = ImageAgent()
        self.subtitle_agent = SubtitleAgent()
        self.video_agent = VideoAgent()
        self.output_manager = OutputManager()
        self.job_manager = JobManager(BASE_DIR)

    def _fix_audio_duration(self, video_path: Path) -> None:
        """Pad short audio to match video duration using ffmpeg."""
        import subprocess, tempfile, shutil

        # Get total video duration
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True, check=True,
        )
        video_dur = float(result.stdout.strip())

        # Get audio stream duration
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "stream=duration",
             "-select_streams", "a:0",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True,
        )

        try:
            audio_dur = float(result.stdout.strip())
        except ValueError:
            logger.warning("Could not read audio duration — skipping padding")
            return

        gap = video_dur - audio_dur
        if gap <= 1.0:
            logger.debug(f"Audio/video duration gap {gap:.1f}s — no padding needed")
            return

        logger.info(f"Audio is {gap:.1f}s shorter than video — padding with silence")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()

        subprocess.run(
            ["ffmpeg", "-y",
             "-i", str(video_path),
             "-af", f"apad=pad_dur={gap}",
             "-c:v", "copy",
             "-c:a", "aac",
             tmp.name],
            check=True, capture_output=True,
        )
        shutil.move(tmp.name, str(video_path))
        logger.info("Audio padding complete")

    def run(
        self,
        format_type: str = "long",
        theme: str = None,
        language: str = "english",
    ) -> dict:
        """
        Execute the full pipeline for one video.

        Args:
            format_type: "shorts" or "long"
            theme: Optional story theme override
            language: "english" | "hindi" | "telugu"

        Returns:
            Result dict with job_id, output_path, quality_score, routed_to
        """
        job_id = unique_job_id(f"{format_type}-{theme or 'random'}-{language}")
        job = self.job_manager.create_job(job_id, format_type, theme)
        workspace = job_workspace(BASE_DIR, job_id)

        logger.info(
            f"Pipeline started | format={format_type} | "
            f"theme={theme or 'random'} | language={language}"
        )

        try:
            # ── 1. Generate Story ────────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_STORY)
            story = self.story_agent.generate_story(
                format_type, theme, language
            )
            job.story_title = story["title"]
            self.job_manager.update(job, story_title=story["title"])
            logger.info(f"📖 Story: '{story['title']}' [{language}]")

            # ── 2. Quality Check ─────────────────────────────────────────────
            job.update_status(JobStatus.QUALITY_CHECK)
            quality = self.story_agent.quality_check(story)
            if not quality.get("approved", False):
                raise ValueError(
                    f"Story rejected by quality check: {quality.get('issues')}"
                )
            self.job_manager.update(job, quality_score=quality.get("score", 0.0))

            # ── 3. Build Scripts ─────────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_SCRIPTS)
            scripts = self.script_agent.build_scripts(story, workspace)

            # Ensure long videos have a proper conclusion
            if format_type == "long" and scripts:
                last = scripts[-1]
                narration = last.get("narration", "")
                conclusion_words = [
                    "lesson", "learned", "remember", "moral",
                    "subscribe", "end", "finally", "thus",
                    "therefore", "always", "never forget",
                ]
                has_conclusion = any(
                    w in narration.lower() for w in conclusion_words
                )
                if not has_conclusion:
                    logger.warning(
                        "Last scene lacks conclusion — appending moral statement"
                    )
                    moral = story.get(
                        "moral", "Kindness and honesty lead to a better world."
                    )
                    scripts[-1]["narration"] = (
                        narration + f" And so, {moral} "
                        f"Thank you for watching! If you enjoyed this story, "
                        f"please like and subscribe for more inspiring stories every week!"
                    )

            image_prompts = self.script_agent.build_image_prompts(story, scripts)

            # ── 4. Generate Voice ────────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_VOICE)
            audio_files = self.voice_agent.generate_all(
                scripts, workspace, language
            )
            audio_durations = [
                self.voice_agent.get_audio_duration(a) for a in audio_files
            ]

            # ── 5. Generate Subtitles ────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_SUBTITLES)
            subtitle_paths = self.subtitle_agent.generate(
                scripts, audio_durations, workspace
            )

            # ── 6. Generate Video (clips or images) ──────────────────────────
            job.update_status(JobStatus.GENERATING_IMAGES)

            if VIDEO_ENGINE == "motion":
                logger.info("Using FLUX images + Ken Burns motion — cinematic pipeline")
                from agents.motion_agent import MotionAgent
                motion = MotionAgent()
                scene_video_files = motion.generate_all(
                    image_prompts, audio_files,
                    audio_durations, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render_from_clips(
                    scene_video_files=scene_video_files,
                    subtitle_paths={},
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                    audio_files=None,
                )
            elif VIDEO_ENGINE == "wavespeed" and WAVESPEED_API_KEY:
                logger.info("Using WAN 2.2 via WaveSpeedAI for video clips")
                from agents.wavespeed_agent import WaveSpeedAgent
                ws = WaveSpeedAgent()
                scene_video_files = ws.generate_all(
                    image_prompts, audio_files,
                    audio_durations, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render_from_clips(
                    scene_video_files=scene_video_files,
                    subtitle_paths=subtitle_paths,
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                    audio_files=audio_files,
                )

            elif VIDEO_ENGINE == "replicate" and REPLICATE_API_KEY:
                logger.info("Using WAN 2.1 via Replicate for video clips")
                from agents.replicate_agent import ReplicateAgent
                rep = ReplicateAgent()
                scene_video_files = rep.generate_all(
                    image_prompts, audio_files,
                    audio_durations, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render_from_clips(
                    scene_video_files=scene_video_files,
                    subtitle_paths=subtitle_paths,
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                )

            elif VIDEO_ENGINE == "veo" and GEMINI_API_KEY:
                logger.info("Using Veo 3.1 via Gemini for video clips")
                from agents.veo_agent import VeoAgent
                veo = VeoAgent()
                scene_video_files = veo.generate_all(
                    image_prompts, audio_files,
                    audio_durations, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render_from_clips(
                    scene_video_files=scene_video_files,
                    subtitle_paths=subtitle_paths,
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                )

            elif VIDEO_ENGINE == "seedance" and SEEDANCE_API_KEY:
                logger.info("Using Seedance 2.0 for cinematic video clips")
                from agents.seedance_agent import SeedanceAgent
                seedance = SeedanceAgent(SEEDANCE_API_KEY, SEEDANCE_BASE_URL)
                scene_video_files = seedance.generate_all(
                    image_prompts, audio_files,
                    audio_durations, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render_from_clips(
                    scene_video_files=scene_video_files,
                    subtitle_paths=subtitle_paths,
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                )

            else:
                # Default: static images (Picsum/HuggingFace/placeholder)
                image_files = self.image_agent.generate_all(
                    image_prompts, workspace, format_type
                )
                job.update_status(JobStatus.RENDERING_VIDEO)
                video_path = self.video_agent.render(
                    image_files=image_files,
                    audio_files=audio_files,
                    audio_durations=audio_durations,
                    subtitle_paths=subtitle_paths,
                    workspace=workspace,
                    story=story,
                    format_type=format_type,
                )

            # ── Fix audio/video duration mismatch ───────────────────────────
            self._fix_audio_duration(video_path)

            # ── 7. Route to Output ───────────────────────────────────────────
            job.update_status(JobStatus.MOVING_OUTPUT)
            final_path, routed_to = self.output_manager.route(
                video_path, story, quality, job_id
            )

            self.job_manager.complete_job(job, str(final_path), routed_to)

            logger.info(
                f"🎬 Pipeline complete! job={job_id} | "
                f"video='{story['title']}' | "
                f"language={language} | "
                f"routed=/{routed_to} | "
                f"score={quality.get('score'):.2f}"
            )

            return {
                "job_id": job_id,
                "title": story["title"],
                "output_path": str(final_path),
                "routed_to": routed_to,
                "quality_score": quality.get("score"),
                "format_type": format_type,
                "language": language,
            }

        except Exception as exc:
            logger.exception(f"Pipeline failed for job {job_id}: {exc}")
            self.job_manager.fail_job(job, str(exc))
            raise