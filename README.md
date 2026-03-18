# 🎬 YouTube Autonomous Content Creation Agent

## Architecture Overview

```
youtube_agent/
├── main.py                     # Entry point + folder watcher
├── config/
│   ├── settings.py             # All configuration constants
│   └── prompts.py              # LLM prompt templates
├── agents/
│   ├── story_agent.py          # Story + character generation (Claude)
│   ├── script_agent.py         # Scene-by-scene narration scripts
│   ├── voice_agent.py          # TTS narration via gTTS / ElevenLabs
│   ├── image_agent.py          # Scene image prompts → Stable Diffusion
│   ├── subtitle_agent.py       # SRT subtitle generation
│   └── video_agent.py          # FFmpeg/MoviePy video assembly
├── core/
│   ├── pipeline.py             # Orchestrates full agent pipeline
│   ├── job_manager.py          # Job state, retry logic
│   └── output_manager.py       # Moves files to /review or /ready_to_upload
├── utils/
│   ├── logger.py               # Structured logging
│   ├── file_utils.py           # File helpers
│   └── retry.py                # Retry decorator
├── output/
│   ├── review/                 # Needs human review before upload
│   └── ready_to_upload/        # Fully auto-approved content
├── assets/
│   ├── music/                  # Royalty-free background tracks
│   └── fonts/                  # Custom subtitle fonts
├── requirements.txt
└── setup.sh
```

## Pipeline Flow

```
[Trigger] → StoryAgent → ScriptAgent → VoiceAgent
                                           ↓
[Output] ← VideoAgent ← SubtitleAgent ← ImageAgent
```

## Quick Start

```bash
chmod +x setup.sh && ./setup.sh
export ANTHROPIC_API_KEY=your_key
python main.py
```
