#!/usr/bin/env bash
# Bootstrap Jarvis on a Debian/Ubuntu host.
# Idempotent: safe to re-run.

set -euo pipefail

log() { printf "\033[1;36m[jarvis]\033[0m %s\n" "$*"; }

if ! command -v apt-get >/dev/null; then
    echo "This script targets Debian/Ubuntu (apt). For Fedora/Arch, port the package list." >&2
    exit 1
fi

log "Installing system packages (sudo required)..."
sudo apt-get update
sudo apt-get install -y \
    build-essential curl git \
    python3 python3-venv python3-dev \
    libnotify-bin pulseaudio-utils \
    speech-dispatcher espeak-ng \
    portaudio19-dev libsndfile1 \
    ffmpeg

if ! command -v uv >/dev/null; then
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

log "Syncing Python deps..."
cd "$(dirname "$0")/.."
uv sync

if [[ ! -f .env ]]; then
    log "Creating .env from template — edit it and add your OPENAI_API_KEY"
    cp .env.example .env
fi

log "Done. Try:  uv run python -m jarvis"
