"""macOS adapter — AppleScript / osascript based."""
from __future__ import annotations

import logging
import shlex
import subprocess

from .base import PlatformAdapter

log = logging.getLogger(__name__)


def _osa(script: str) -> None:
    subprocess.run(["osascript", "-e", script], check=False)


class MacOSAdapter(PlatformAdapter):
    name = "macos"

    def notify(self, title: str, body: str) -> None:
        safe_title = title.replace('"', "'")
        safe_body = body.replace('"', "'")
        _osa(f'display notification "{safe_body}" with title "{safe_title}"')

    def open_app(self, app: str) -> None:
        subprocess.run(["open", "-a", app], check=False)

    def set_volume(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        _osa(f"set volume output volume {percent}")

    def speak_fallback(self, text: str) -> None:
        subprocess.run(["say", text], check=False)
