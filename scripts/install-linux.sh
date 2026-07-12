#!/usr/bin/env bash
# Bootstrap Jarvis on a Debian/Ubuntu host.
# Idempotent: safe to re-run.

set -euo pipefail

log() { printf "\033[1;36m[jarvis]\033[0m %s\n" "$*"; }

usage() {
    cat <<'EOF'
Usage: scripts/install-linux.sh [--skip-system-packages] [--skip-input-group]

Without options, installs required Ubuntu packages (requires an interactive
sudo password prompt), then installs uv and Python dependencies.

  --skip-system-packages  Skip apt packages and install only uv/Python deps.
                          System features such as volume control may be absent.
  --skip-input-group      Do not add $USER to the 'input' group; you will
                          be unable to use the global voice hotkey until you
                          add yourself manually.
EOF
}

skip_system_packages=false
skip_input_group=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-system-packages) skip_system_packages=true ;;
        --skip-input-group) skip_input_group=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

if ! command -v apt-get >/dev/null; then
    echo "This script targets Debian/Ubuntu (apt). For Fedora/Arch, port the package list." >&2
    exit 1
fi

if [[ "$skip_system_packages" == true ]]; then
    log "Skipping system packages; volume, notifications, and fallback speech may be unavailable."
else
    log "Checking sudo access for system packages..."
    if ! sudo -v; then
        echo "Could not authenticate sudo. Run this script in your own terminal and enter your password," >&2
        echo "or use --skip-system-packages to install only uv and Python dependencies." >&2
        exit 1
    fi

    apt_packages=(
        build-essential curl git
        python3 python3-venv python3-dev
        libnotify-bin pulseaudio-utils
        speech-dispatcher espeak-ng
        portaudio19-dev libsndfile1
        ffmpeg
    )

    apt_install() {
        sudo apt-get install -y "${apt_packages[@]}"
    }

    log "Installing system packages..."
    sudo apt-get update
    if ! apt_install; then
        log "apt reported unmet dependencies; attempting automatic recovery..."
        log "Running: sudo apt-get -y full-upgrade"
        sudo apt-get -y full-upgrade || true
        log "Running: sudo apt-get -f install -y"
        sudo apt-get -f install -y || true
        log "Retrying package install..."
        if ! apt_install; then
            cat <<'MSG' >&2

[jarvis] Automatic recovery did not resolve the apt dependency problem.
        Please inspect the output above and, if needed, run manually:

            sudo apt-get update
            sudo apt-get -y full-upgrade
            sudo apt-get -f install

        Then re-run: bash scripts/install-linux.sh
MSG
            exit 1
        fi
    fi
fi

if ! command -v uv >/dev/null; then
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

log "Syncing Python deps..."
cd "$(dirname "$0")/.."
uv sync

if [[ "$skip_input_group" == false ]]; then
    if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
        log "User $USER is already in the 'input' group; voice hotkey ready."
    else
        log "Adding $USER to the 'input' group (needed for the voice hotkey)..."
        log "You will need to log out and back in for this to take effect."
        if ! sudo usermod -aG input "$USER"; then
            echo "[jarvis] Could not add $USER to input group. Re-run with --skip-input-group to bypass." >&2
        fi
    fi
fi

if [[ ! -f .env ]]; then
    log "Creating .env from template — edit it and add your OPENAI_API_KEY"
    cp .env.example .env
fi

log "Done. Try:  uv run python -m jarvis"
