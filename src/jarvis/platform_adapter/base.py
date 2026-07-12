"""Abstract platform adapter. Keep this list short and Phase-appropriate."""
from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    name: str = "abstract"

    @abstractmethod
    def notify(self, title: str, body: str) -> None:
        """Show a desktop notification."""

    @abstractmethod
    def open_app(self, app: str) -> None:
        """Open an application by name or bundle id."""

    @abstractmethod
    def set_volume(self, percent: int) -> None:
        """Set system output volume 0-100."""

    @abstractmethod
    def speak_fallback(self, text: str) -> None:
        """OS-native TTS as a last resort when Piper/ElevenLabs unavailable."""

    @abstractmethod
    def install_app(self, package: str) -> str:
        """Install a desktop application by package name.

        Returns a short human-readable description of what was installed
        (for example the package manager used). May prompt for sudo in the
        controlling terminal.
        """


    def play_music(self, query: str, service: str = "spotify") -> str:  # noqa: ARG002
        raise RuntimeError("play_music not supported on this platform yet")
