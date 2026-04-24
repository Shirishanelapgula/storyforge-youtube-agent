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
    """
    Create a safe filename preserving meaning.
    For non-ASCII titles (Telugu/Hindi), uses hash.
    """
    import unicodedata
    import hashlib

    # Try to transliterate unicode to ASCII
    try:
        normalized = unicodedata.normalize('NFKD', name)
        ascii_version = normalized.encode('ascii', 'ignore').decode('ascii').strip()
    except Exception:
        ascii_version = ""

    if len(ascii_version) >= 3:
        keep = set(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789_-"
        )
        # Replace spaces and unsafe chars with underscore
        clean = "".join(c if c in keep else "_" for c in ascii_version)
        # Remove consecutive underscores
        while "__" in clean:
            clean = clean.replace("__", "_")
        clean = clean.strip("_")
        return clean[:60] if clean else "story"

    # Non-ASCII (Telugu/Hindi) — use hash
    words = name.strip().split()
    if words:
        short = "_".join(words[:3])
        safe = "".join(
            c if c.isalnum() or c == "_" else "_"
            for c in short
        )
        while "__" in safe:
            safe = safe.replace("__", "_")
        safe = safe.strip("_")
        if len(safe) >= 3:
            return safe[:60]

    return "story_" + hashlib.md5(name.encode()).hexdigest()[:8]
