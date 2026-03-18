"""
utils/file_utils.py
File and directory helpers used throughout the pipeline.
"""

import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("file_utils")


def ensure_dirs(*dirs):
    """Create directories if they don't exist."""
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


def save_json(data: dict, path: Path) -> None:
    """Serialize dict to pretty-printed JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.debug(f"Saved JSON → {path}")


def load_json(path: Path) -> dict:
    """Load JSON file into dict."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def unique_job_id(title: str) -> str:
    """Generate a short unique ID based on title + timestamp."""
    raw = f"{title}-{datetime.now().isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def job_workspace(base_dir: Path, job_id: str) -> Path:
    """Return (and create) a per-job temp workspace directory."""
    ws = base_dir / "workspace" / job_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def move_to_output(src: Path, dest_dir: Path) -> Path:
    """Move a file to the output directory, returning new path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.move(str(src), str(dest))
    logger.info(f"Moved {src.name} → {dest_dir}")
    return dest


def sanitize_filename(name: str) -> str:
    """Strip unsafe characters from filenames."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ")
    return "".join(c if c in keep else "_" for c in name).strip().replace(" ", "_")
