#!/usr/bin/env bash
# setup.sh — One-shot environment setup for YouTube Content Agent

set -euo pipefail

echo "═══════════════════════════════════════════════════"
echo "  YouTube Autonomous Content Agent — Setup"
echo "═══════════════════════════════════════════════════"

# ── 1. Python version check ───────────────────────────────────────────────────
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✔  Python: $python_version"

# ── 2. FFmpeg check ───────────────────────────────────────────────────────────
if command -v ffmpeg &>/dev/null; then
    echo "✔  FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
else
    echo "⚠  FFmpeg not found. Installing..."
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install ffmpeg
    elif [[ -f /etc/debian_version ]]; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    else
        echo "❌  Please install FFmpeg manually: https://ffmpeg.org/download.html"
        exit 1
    fi
fi

# ── 3. Virtual environment ────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "Creating virtual environment…"
    python3 -m venv venv
fi
source venv/bin/activate
echo "✔  Virtual env activated"

# ── 4. Python packages ────────────────────────────────────────────────────────
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✔  Python packages installed"

# ── 5. Create output directories ─────────────────────────────────────────────
mkdir -p output/review output/ready_to_upload workspace logs inbox assets/fonts assets/music
echo "✔  Output directories created"

# ── 6. .env template ─────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
cat > .env << 'EOF'
# Required
ANTHROPIC_API_KEY=your_anthropic_key_here

# Optional: High-quality voice (leave blank to use gTTS)
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Optional: AI scene images (leave blank to use colored placeholders)
STABILITY_API_KEY=

# TTS engine: "gtts" | "elevenlabs"
TTS_ENGINE=gtts

# Image engine: "placeholder" | "stability"
IMAGE_ENGINE=placeholder
EOF
    echo "✔  .env template created — add your API keys!"
else
    echo "✔  .env already exists"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Setup complete! Next steps:"
echo "  1. Edit .env and add your ANTHROPIC_API_KEY"
echo "  2. source venv/bin/activate"
echo "  3. python main.py --format long"
echo "═══════════════════════════════════════════════════"
