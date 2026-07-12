#!/usr/bin/env bash
# Quick dev launcher.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m jarvis "$@"
