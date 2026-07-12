"""Linux adapter — freedesktop / dbus / shell utilities.

Requires (install lazily as features are used):
  - `notify-send` (libnotify) for notifications
  - `pactl` (PipeWire/PulseAudio) for volume
  - `spd-say` or `espeak-ng` for fallback TTS
  - a desktop `.desktop` launcher on PATH via `gtk-launch` (or just `xdg-open`)
"""
from __future__ import annotations

import logging
import shutil
import subprocess

from .base import PlatformAdapter

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> None:
    if not shutil.which(cmd[0]):
        log.warning("missing binary: %s (skipping: %s)", cmd[0], " ".join(cmd))
        return
    subprocess.run(cmd, check=False)


class LinuxAdapter(PlatformAdapter):
    name = "linux"

    def notify(self, title: str, body: str) -> None:
        _run(["notify-send", title, body])

    def open_app(self, app: str) -> None:
        # Try gtk-launch first (uses .desktop names), fall back to xdg-open or plain exec.
        if shutil.which("gtk-launch"):
            _run(["gtk-launch", app])
        elif shutil.which("xdg-open"):
            _run(["xdg-open", app])
        else:
            _run([app])

    def set_volume(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])

    def speak_fallback(self, text: str) -> None:
        if shutil.which("spd-say"):
            _run(["spd-say", text])
        elif shutil.which("espeak-ng"):
            _run(["espeak-ng", text])
        else:
            log.warning("no fallback TTS installed (spd-say or espeak-ng)")
