#!/usr/bin/env bash
# Bootstrap Jarvis on macOS (dev machine).
set -euo pipefail

log() { printf "\033[1;36m[jarvis]\033[0m %s\n" "$*"; }

if ! command -v brew >/dev/null; then
    echo "Homebrew required. Install from https://brew.sh first." >&2
    exit 1
fi

log "Installing system packages..."
brew install portaudio ffmpeg

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
