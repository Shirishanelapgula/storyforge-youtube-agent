"""
main.py
Entry point for the YouTube Autonomous Content Agent.

Modes:
  python main.py                         → Run one long video (default)
  python main.py --format shorts         → Run one Shorts video
  python main.py --theme "honesty"       → Run with specific theme
  python main.py --watch                 → Watch inbox/ folder for job files
  python main.py --batch 5               → Generate 5 videos sequentially
"""
from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import sys
import time
from pathlib import Path

from core.pipeline import ContentPipeline
from config.settings import WATCH_DIR, BASE_DIR
from utils.logger import get_logger
from utils.file_utils import ensure_dirs

logger = get_logger("main")


def run_single(format_type: str, theme: str = None, language: str = "english") -> None:
    pipeline = ContentPipeline()
    logger.info(f"Starting single job | format={format_type} | theme={theme or 'random'} | language={language}")
    result = pipeline.run(format_type=format_type, theme=theme, language=language)
    print("\n" + "="*60)
    print(f"✅ DONE: {result['title']}")
    print(f"   Format:  {result['format_type']}")
    print(f"   Score:   {result['quality_score']:.2f}")
    print(f"   Routed:  /{result['routed_to']}/")
    print(f"   File:    {result['output_path']}")
    print("="*60 + "\n")


def run_batch(count: int, format_type: str) -> None:
    """Run multiple videos sequentially."""
    logger.info(f"Starting batch of {count} {format_type} videos")
    for i in range(1, count + 1):
        logger.info(f"Batch [{i}/{count}]")
        try:
            run_single(format_type)
        except Exception as e:
            logger.error(f"Batch job {i} failed: {e}")
        time.sleep(2)


def watch_inbox() -> None:
    """
    Watch the inbox/ folder for .json job files.
    Job file format:
        {"format_type": "long", "theme": "honesty and integrity"}
    """
    inbox = Path(WATCH_DIR)
    inbox.mkdir(parents=True, exist_ok=True)
    processed_dir = inbox / "processed"
    processed_dir.mkdir(exist_ok=True)

    logger.info(f"👀 Watching {inbox} for job files… (Ctrl+C to stop)")
    pipeline = ContentPipeline()

    while True:
        job_files = list(inbox.glob("*.json"))
        for job_file in job_files:
            try:
                with open(job_file) as f:
                    params = json.load(f)
                format_type = params.get("format_type", "long")
                theme = params.get("theme", None)
                logger.info(f"📥 Picked up job file: {job_file.name}")

                result = pipeline.run(format_type=format_type, theme=theme)
                logger.info(f"✅ Job complete: {result['title']}")

                # Move processed file
                dest = processed_dir / job_file.name
                job_file.rename(dest)

            except Exception as e:
                logger.error(f"Failed processing {job_file.name}: {e}")
                # Move to error folder
                err_dir = inbox / "errors"
                err_dir.mkdir(exist_ok=True)
                job_file.rename(err_dir / job_file.name)

        time.sleep(5)  # Poll interval


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Autonomous Content Creation Agent"
    )
    parser.add_argument(
        "--format", choices=["long", "shorts"], default="long",
        help="Video format: 'long' (5-10 min) or 'shorts' (< 60s)"
    )
    parser.add_argument("--theme", type=str, default=None,
                    help="Story theme (optional)")
    parser.add_argument(
        "--language", choices=["english", "hindi", "telugu"],
        default="english", help="Story language"
   )
    parser.add_argument("--watch", action="store_true",
                        help="Watch inbox/ folder for job files")
    parser.add_argument("--batch", type=int, default=0,
                        help="Generate N videos sequentially")

    args = parser.parse_args()

    # Ensure output directories exist
    ensure_dirs(
        BASE_DIR / "output" / "review",
        BASE_DIR / "output" / "ready_to_upload",
        BASE_DIR / "workspace",
        BASE_DIR / "logs",
        BASE_DIR / "inbox",
    )

    if args.watch:
        watch_inbox()
    elif args.batch > 0:
        run_batch(args.batch, args.format)
    else:
        run_single(args.format, args.theme, args.language)


if __name__ == "__main__":
    main()
