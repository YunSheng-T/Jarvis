"""macOS adapter — AppleScript / osascript based."""
from __future__ import annotations

import logging
import subprocess

from .base import PlatformAdapter

log = logging.getLogger(__name__)


def _osa(script: str) -> None:
    completed = subprocess.run(["osascript", "-e", script], check=False)
    if completed.returncode:
        raise RuntimeError(f"osascript failed with exit code {completed.returncode}")


class MacOSAdapter(PlatformAdapter):
    name = "macos"

    def notify(self, title: str, body: str) -> None:
        safe_title = title.replace('"', "'")
        safe_body = body.replace('"', "'")
        _osa(f'display notification "{safe_body}" with title "{safe_title}"')

    def open_app(self, app: str) -> None:
        completed = subprocess.run(["open", "-a", app], check=False)
        if completed.returncode:
            raise RuntimeError(f"could not open application: {app}")

    def set_volume(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        _osa(f"set volume output volume {percent}")

    def speak_fallback(self, text: str) -> None:
        subprocess.run(["say", text], check=False)


    def install_app(self, package: str) -> str:
        import shutil
        if not shutil.which("brew"):
            raise RuntimeError(
                "Homebrew (brew) is required to install applications on macOS. "
                "Install it from https://brew.sh and try again."
            )
        completed = subprocess.run(["brew", "install", "--cask", package], check=False)
        if completed.returncode:
            completed = subprocess.run(["brew", "install", package], check=False)
        if completed.returncode:
            raise RuntimeError(f"brew install failed for {package}")
        return f"installed {package} via brew"
