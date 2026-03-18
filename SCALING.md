# Scaling & Production Deployment Guide

## Current Architecture (Single Machine)

```
main.py → ContentPipeline → 6 Agents → output/
```

---

## Phase 2: Task Queue (Celery + Redis)

Replace the `watch_inbox` loop with proper async workers.

```python
# workers/celery_app.py
from celery import Celery
from core.pipeline import ContentPipeline

app = Celery("youtube_agent", broker="redis://localhost:6379/0")

@app.task(bind=True, max_retries=3)
def create_video(self, format_type: str, theme: str = None):
    try:
        pipeline = ContentPipeline()
        return pipeline.run(format_type=format_type, theme=theme)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

**Deploy:**
```bash
pip install celery redis
celery -A workers.celery_app worker --concurrency=4
```

---

## Phase 3: Docker Containerization

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py", "--watch"]
```

```yaml
# docker-compose.yml
version: "3.9"
services:
  agent:
    build: .
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./output:/app/output
    depends_on: [redis]
  redis:
    image: redis:7-alpine
  worker:
    build: .
    command: celery -A workers.celery_app worker --concurrency=4
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

---

## Phase 4: Cloud Storage (S3/GCS)

```python
# utils/cloud_storage.py
import boto3

def upload_to_s3(local_path, bucket, key):
    s3 = boto3.client("s3")
    s3.upload_file(str(local_path), bucket, key)
    return f"s3://{bucket}/{key}"
```

Modify `OutputManager.route()` to call `upload_to_s3()` after local copy.

---

## Phase 5: YouTube Auto-Upload (YouTube Data API v3)

```python
# agents/upload_agent.py
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_video(video_path, metadata, credentials):
    youtube = build("youtube", "v3", credentials=credentials)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": metadata["tags"],
                "categoryId": "22",  # People & Blogs
            },
            "status": {"privacyStatus": "public"},
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )
    return request.execute()
```

---

## Phase 6: Monitoring Dashboard

```python
# monitoring/dashboard.py  (FastAPI)
from fastapi import FastAPI
from utils.file_utils import load_json
from pathlib import Path

app = FastAPI()

@app.get("/jobs")
def list_jobs():
    workspace = Path("workspace")
    jobs = []
    for job_dir in workspace.iterdir():
        state_file = job_dir / "job_state.json"
        if state_file.exists():
            jobs.append(load_json(state_file))
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

@app.get("/stats")
def stats():
    review = len(list(Path("output/review").glob("*.mp4")))
    upload = len(list(Path("output/ready_to_upload").glob("*.mp4")))
    return {"review_queue": review, "ready_to_upload": upload}
```

---

## Scaling Checklist

| Phase | Feature | Tools |
|-------|---------|-------|
| 1 | Single machine + folder watch | Python + FFmpeg |
| 2 | Async job queue | Celery + Redis |
| 3 | Containerization | Docker Compose |
| 4 | Cloud storage | AWS S3 / GCS |
| 5 | Auto YouTube upload | YouTube Data API v3 |
| 6 | Monitoring dashboard | FastAPI + React |
| 7 | Multi-language voices | ElevenLabs multilingual |
| 8 | A/B thumbnail testing | Custom image generation |
| 9 | Analytics feedback loop | YouTube Analytics API → Claude |

---

## Monetization Strategy

1. **Niche channels** — Run separate instances per niche (kids fables, business lessons, nature stories)
2. **Batch scheduling** — Generate 7 videos on Sunday, schedule M–Su via YouTube Studio
3. **SEO optimization** — Claude generates keyword-rich titles + descriptions per video
4. **Shorts as trailers** — Auto-generate a Short version of every Long video for cross-promotion
5. **Quality gate** — Only `score >= 0.85` goes to `ready_to_upload`; rest queued for human review
