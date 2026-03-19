"""
core/output_manager.py
Routes completed videos to /review or /ready_to_upload based on quality score.
Writes metadata JSON alongside each video.
"""

import shutil
from pathlib import Path
from datetime import datetime

from config.settings import AUTO_APPROVE_THRESHOLD, REVIEW_DIR, UPLOAD_DIR
from utils.logger import get_logger
from utils.file_utils import save_json, ensure_dirs

logger = get_logger("output_manager")


class OutputManager:
    """Moves finished videos + metadata to the correct output folder."""

    def __init__(self):
        ensure_dirs(REVIEW_DIR, UPLOAD_DIR)

    def route(
        self,
        video_path: Path,
        story: dict,
        quality_result: dict,
        job_id: str,
    ) -> tuple[Path, str]:
        """
        Copy the video and metadata to the appropriate output directory.

        Returns:
            (final_video_path, "review" | "ready_to_upload")
        """
        score = quality_result.get("score", 0.0)
        approved = quality_result.get("approved", False)

        dest_dir = UPLOAD_DIR if (approved and score >= AUTO_APPROVE_THRESHOLD) else REVIEW_DIR
        label = "ready_to_upload" if dest_dir == UPLOAD_DIR else "review"

        dest_dir.mkdir(parents=True, exist_ok=True)
        # Add language prefix to filename for easy identification
        language = story.get("language", "english")
        lang_prefix = {"english": "EN", "hindi": "HI", "telugu": "TE"}.get(language, "EN")
        new_name = f"{lang_prefix}_{video_path.name}"
        dest_video = dest_dir / new_name

        shutil.copy2(str(video_path), str(dest_video))
        logger.info(f"Video → /{label}/{video_path.name} (score={score:.2f})")

        # Write metadata sidecar
        metadata = {
            "job_id": job_id,
            "title": story.get("title"),
            "moral": story.get("moral"),
            "theme": story.get("theme"),
            "format": story.get("format_type"),
            "characters": [c["name"] for c in story.get("characters", [])],
            "tags": story.get("tags", []),
            "description": story.get("description", ""),
            "call_to_action": story.get("call_to_action", ""),
            "quality_score": score,
            "auto_approved": label == "ready_to_upload",
            "routed_to": label,
            "generated_at": datetime.now().isoformat(),
        }

        meta_path = dest_dir / (video_path.stem + "_metadata.json")
        save_json(metadata, meta_path)
        logger.info(f"Metadata saved: {meta_path.name}")

        return dest_video, label
