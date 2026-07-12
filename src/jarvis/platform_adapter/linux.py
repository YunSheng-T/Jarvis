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
        message = f"required command is not installed: {cmd[0]}"
        log.warning("%s (would run: %s)", message, " ".join(cmd))
        raise RuntimeError(message)

    completed = subprocess.run(cmd, check=False)
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(cmd)}")


def _spawn(cmd: list[str]) -> None:
    """Start a long-running GUI process without blocking Jarvis.

    The process is detached from Jarvis; we only wait briefly to catch immediate
    launcher errors (for example ``gtk-launch: no such application``) so that
    genuine failures still propagate.
    """
    if not shutil.which(cmd[0]):
        message = f"required command is not installed: {cmd[0]}"
        log.warning("%s (would run: %s)", message, " ".join(cmd))
        raise RuntimeError(message)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=0.6)
    except subprocess.TimeoutExpired:
        return  # still running -> assume the app is starting up

    if proc.returncode:
        detail = (stderr or stdout or b"").decode(errors="replace").strip()
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}"
            + (f": {detail}" if detail else "")
        )


class LinuxAdapter(PlatformAdapter):
    name = "linux"

    def notify(self, title: str, body: str) -> None:
        _run(["notify-send", title, body])

    def open_app(self, app: str) -> None:
        """Open a desktop app, trying common launcher schemes in order.

        Handles the case where snap-installed apps expose the binary on PATH
        (for example ``/snap/bin/spotify``) but do not register a desktop
        entry under the plain name, which makes ``gtk-launch spotify`` fail.
        """
        candidates: list[list[str]] = []
        if shutil.which("gtk-launch"):
            candidates.append(["gtk-launch", app])
            # Snap desktop files usually look like "<name>_<name>.desktop".
            candidates.append(["gtk-launch", f"{app}_{app}"])
        if shutil.which(app):
            candidates.append([app])
        if shutil.which("xdg-open"):
            candidates.append(["xdg-open", app])

        if not candidates:
            raise RuntimeError(f"no launcher available for {app!r}")

        errors: list[str] = []
        for cmd in candidates:
            try:
                _spawn(cmd)
                return
            except RuntimeError as exc:
                errors.append(str(exc))
        raise RuntimeError(f"could not open {app!r}: {'; '.join(errors)}")

    def play_music(self, query: str, service: str = "spotify") -> str:
        if service.lower() != "spotify":
            raise RuntimeError(f"unsupported music service: {service}")
        uri = "spotify:search:" + query.strip().replace(" ", "+")
        if shutil.which("spotify"):
            _spawn(["spotify", "--uri", uri])
        elif shutil.which("xdg-open"):
            _spawn(["xdg-open", uri])
        else:
            raise RuntimeError(
                "Spotify does not appear to be installed. Ask me to install it first."
            )
        return f"opened Spotify search for {query!r}"

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


    _APT_ALIASES = {
        "spotify": None,
        "chrome": "google-chrome-stable",
        "google chrome": "google-chrome-stable",
        "vscode": "code",
        "visual studio code": "code",
    }

    _SNAP_ALIASES = {
        "spotify": "spotify",
        "vscode": "code",
        "visual studio code": "code",
        "chromium": "chromium",
    }

    def install_app(self, package: str) -> str:
        key = package.strip().lower()
        errors: list[str] = []

        snap_name = self._SNAP_ALIASES.get(key, key)
        if shutil.which("snap") and snap_name:
            try:
                _run(["sudo", "snap", "install", snap_name])
                return f"installed {snap_name} via snap"
            except RuntimeError as exc:
                errors.append(f"snap: {exc}")

        apt_name = self._APT_ALIASES.get(key, key) if key in self._APT_ALIASES else key
        if shutil.which("apt-get") and apt_name:
            try:
                _run(["sudo", "apt-get", "update"])
                _run(["sudo", "apt-get", "install", "-y", apt_name])
                return f"installed {apt_name} via apt"
            except RuntimeError as exc:
                errors.append(f"apt: {exc}")

        detail = "; ".join(errors) if errors else "no supported package manager found"
        raise RuntimeError(f"could not install {package!r}: {detail}")
