import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pathlib import Path
import uvicorn
import hashlib
import time
import traceback

from core.pipeline import ContentPipeline
from utils.logger import get_logger

logger = get_logger("api")
app = FastAPI(title="StoryForge - YouTube Content Agent")
pipeline = ContentPipeline()

TEMPLATES_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR = Path(__file__).parent / "output"

jobs = {}


def run_pipeline(job_id: str, format_type: str, theme: str, language: str):
    """Run pipeline in background and track real status."""
    original_update = None
    try:
        jobs[job_id] = {
            "status": "generating_story",
            "progress": 1,
            "language": language,
            "format": format_type,
        }

        original_update = pipeline.job_manager.update
        status_map = {
            "generating_story":     1,
            "quality_check":        2,
            "generating_scripts":   3,
            "generating_voice":     4,
            "generating_images":    4,
            "generating_subtitles": 4,
            "rendering_video":      5,
            "moving_output":        5,
            "completed":            6,
            "failed":               0,
        }

        def patched_update(job, **kwargs):
            original_update(job, **kwargs)
            status_val = (
                str(job.status.value)
                if hasattr(job.status, "value")
                else str(job.status)
            )
            if status_val in status_map:
                jobs[job_id]["status"] = status_val
                jobs[job_id]["progress"] = status_map[status_val]

        pipeline.job_manager.update = patched_update

        result = pipeline.run(
            format_type=format_type,
            theme=theme or None,
            language=language,          # ← passed directly from UI
        )

        jobs[job_id] = {
            "status": "completed",
            "progress": 6,
            "title": result.get("title"),
            "routed_to": result.get("routed_to"),
            "quality_score": result.get("quality_score"),
            "format_type": format_type,
            "language": language,
        }

    except Exception as e:
        full_error = traceback.format_exc()
        logger.error(f"Pipeline failed for job {job_id}: {full_error}")
        jobs[job_id] = {
            "status": "failed",
            "progress": 0,
            "error": str(e),
            "language": language,
        }
    finally:
        if original_update is not None:
            pipeline.job_manager.update = original_update


@app.get("/", response_class=HTMLResponse)
def home():
    index = TEMPLATES_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return JSONResponse({"status": "running"})


@app.post("/generate")
def generate(
    format_type: str = "shorts",
    theme: str = None,
    language: str = "english",          # ← received from UI
    background_tasks: BackgroundTasks = None,
):
    job_id = hashlib.md5(
        f"{theme}-{language}-{time.time()}".encode()
    ).hexdigest()[:10]
    jobs[job_id] = {"status": "starting", "progress": 0}
    background_tasks.add_task(
        run_pipeline, job_id, format_type, theme or "", language
    )
    return {
        "status": "started",
        "format": format_type,
        "theme": theme or "random",
        "language": language,
        "job_id": job_id,
    }


@app.get("/job/{job_id}")
def job_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found", "progress": 0})


@app.get("/videos")
def list_videos():
    ready_dir = OUTPUT_DIR / "ready_to_upload"
    review_dir = OUTPUT_DIR / "review"
    ready  = [f.name for f in ready_dir.glob("*.mp4")] if ready_dir.exists() else []
    review = [f.name for f in review_dir.glob("*.mp4")] if review_dir.exists() else []
    return {"ready_to_upload": ready, "review": review}


@app.get("/download/{folder}/{filename}")
def download_video(folder: str, filename: str):
    allowed = {"ready_to_upload", "review"}
    if folder not in allowed:
        return JSONResponse({"error": "Invalid folder"}, status_code=400)
    path = OUTPUT_DIR / folder / filename
    if not path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4", filename=filename)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)