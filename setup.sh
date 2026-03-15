#!/usr/bin/env bash
# yt2tg setup for Linux / Google Colab
# Usage: bash setup.sh

set -e

echo "═══ yt2tg Setup (Linux/Colab) ═══"

# Create virtualenv (skip in Colab where we just use the base env)
if [ -z "$COLAB_JUPYTER_IP" ]; then
    python3 -m venv .venv
    source .venv/bin/activate
    echo "Activated virtualenv: .venv"
else
    echo "Running in Colab — skipping venv"
fi

# Install Python deps
pip install -q --upgrade pip
pip install -q pyrogram tgcrypto yt-dlp

# Verify yt-dlp
if command -v yt-dlp &>/dev/null; then
    echo "yt-dlp: $(yt-dlp --version)"
else
    echo "[WARN] yt-dlp not in PATH — place yt-dlp binary in this folder"
fi

echo ""
echo "✓ Done. Next steps:"
echo "  1. Place your cookies.txt in this folder"
echo "  2. python yt2tg.py --setup"
echo "  3. python yt2tg.py 'YOUTUBE_URL'"
