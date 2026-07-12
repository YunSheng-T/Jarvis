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
