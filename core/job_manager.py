"""
core/job_manager.py
Manages job state, retry tracking, and status persistence.
"""

import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from utils.logger import get_logger
from utils.file_utils import save_json

logger = get_logger("job_manager")


class JobStatus(str, Enum):
    PENDING = "pending"
    GENERATING_STORY = "generating_story"
    QUALITY_CHECK = "quality_check"
    GENERATING_SCRIPTS = "generating_scripts"
    GENERATING_VOICE = "generating_voice"
    GENERATING_IMAGES = "generating_images"
    GENERATING_SUBTITLES = "generating_subtitles"
    RENDERING_VIDEO = "rendering_video"
    MOVING_OUTPUT = "moving_output"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    format_type: str
    theme: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    story_title: Optional[str] = None
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None
    quality_score: float = 0.0

    def update_status(self, status: JobStatus, error: str = None):
        self.status = status
        self.updated_at = time.time()
        if error:
            self.error = error
        logger.info(f"[Job {self.job_id}] → {status.value}"
                    + (f" | Error: {error}" if error else ""))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class JobManager:
    """Tracks and persists all job state."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.jobs: dict[str, Job] = {}

    def create_job(self, job_id: str, format_type: str, theme: str = None) -> Job:
        job = Job(job_id=job_id, format_type=format_type, theme=theme)
        self.jobs[job_id] = job
        self._persist(job)
        logger.info(f"Created job {job_id} | format={format_type} | theme={theme}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def update(self, job: Job, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = time.time()
        self._persist(job)

    def fail_job(self, job: Job, error: str) -> None:
        job.update_status(JobStatus.FAILED, error=error)
        self._persist(job)

    def complete_job(self, job: Job, output_path: str, output_dir: str) -> None:
        job.output_path = output_path
        job.output_dir = output_dir
        job.update_status(JobStatus.COMPLETED)
        self._persist(job)

    def _persist(self, job: Job) -> None:
        """Save job state as JSON to disk."""
        job_dir = self.workspace_root / "workspace" / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        save_json(job.to_dict(), job_dir / "job_state.json")
