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
    BASE_DIR, SEEDANCE_API_KEY, SEEDANCE_BASE_URL, VIDEO_ENGINE
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
            image_prompts = self.script_agent.build_image_prompts(story, scripts)

            # ── 4. Generate Voice ────────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_VOICE)
            audio_files = self.voice_agent.generate_all(
                scripts, workspace, language   # ← language passed here
            )
            audio_durations = [
                self.voice_agent.get_audio_duration(a) for a in audio_files
            ]

            # ── 5. Generate Subtitles ────────────────────────────────────────
            job.update_status(JobStatus.GENERATING_SUBTITLES)
            subtitle_paths = self.subtitle_agent.generate(
                scripts, audio_durations, workspace
            )

            # ── 6. Generate Images or Seedance Clips ─────────────────────────
            job.update_status(JobStatus.GENERATING_IMAGES)

            if VIDEO_ENGINE == "seedance" and SEEDANCE_API_KEY:
                logger.info("Using Seedance 2.0 for cinematic video clips")
                from agents.seedance_agent import SeedanceAgent
                seedance = SeedanceAgent(SEEDANCE_API_KEY, SEEDANCE_BASE_URL)
                scene_video_files = seedance.generate_all(
                    image_prompts, audio_files, audio_durations,
                    workspace, format_type
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