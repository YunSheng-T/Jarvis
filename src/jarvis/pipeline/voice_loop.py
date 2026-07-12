"""End-to-end voice turn: capture → transcribe → brain → speak.

This module intentionally does *not* own the hotkey — the caller decides when
a turn begins and ends. That keeps the loop testable and independent of the
platform-specific hotkey plumbing that follows in the next step.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from jarvis.pipeline.audio_io import (
    RecorderConfig,
    record_until_silence,
)

log = logging.getLogger(__name__)

Recorder = Callable[[RecorderConfig], bytes]
Transcriber = Callable[[bytes], "Transcription"]
BrainReplier = Callable[[str], Iterator[str]]
Speaker = Callable[[Iterator[str]], None]
FallbackSpeaker = Callable[[str], None]


@dataclass(slots=True)
class Transcription:
    """Loose duck-typed shape shared with jarvis.pipeline.asr.Transcription."""

    text: str
    language: str = ""
    duration_ms: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class VoiceTurn:
    """The observable result of a single voice turn."""

    transcript: str
    reply: str
    language: str = ""
    aborted: bool = False
    reason: str = ""
    fragments: list[str] = field(default_factory=list)


DEFAULT_EMPTY_HINT = "I didn't catch that — please try again."


@dataclass
class VoiceLoop:
    """Wires the four stages together with pluggable collaborators.

    Every stage is a plain callable so tests can substitute stubs and Phase 3
    can inject a wake-word gated recorder without touching this class.
    """

    recorder: Recorder
    transcriber: Transcriber
    brain: BrainReplier
    speaker: Speaker
    fallback_speaker: FallbackSpeaker | None = None
    empty_hint: str = DEFAULT_EMPTY_HINT

    def run_turn(self, config: RecorderConfig | None = None) -> VoiceTurn:
        cfg = config or RecorderConfig()
        pcm = self.recorder(cfg)
        if not pcm:
            return self._abort("no audio captured")

        transcription = self.transcriber(pcm)
        transcript = transcription.text.strip()
        if not transcript:
            self._speak_hint(self.empty_hint)
            return self._abort("empty transcript", language=transcription.language)

        fragments: list[str] = []

        def _tee(chunks: Iterator[str]) -> Iterator[str]:
            for chunk in chunks:
                fragments.append(chunk)
                yield chunk

        stream = self.brain(transcript)
        try:
            self.speaker(_tee(stream))
        except Exception as exc:  # noqa: BLE001 — surface, do not crash the loop
            log.exception("voice turn playback failed")
            return VoiceTurn(
                transcript=transcript,
                reply="".join(fragments),
                language=transcription.language,
                aborted=True,
                reason=f"playback error: {exc}",
                fragments=fragments,
            )

        return VoiceTurn(
            transcript=transcript,
            reply="".join(fragments),
            language=transcription.language,
            fragments=fragments,
        )

    def _speak_hint(self, text: str) -> None:
        if self.fallback_speaker is None:
            return
        try:
            self.fallback_speaker(text)
        except Exception:  # noqa: BLE001
            log.exception("fallback speaker failed")

    @staticmethod
    def _abort(reason: str, language: str = "") -> VoiceTurn:
        return VoiceTurn(
            transcript="",
            reply="",
            language=language,
            aborted=True,
            reason=reason,
        )


def build_default(brain: Any, speaker_stream: Speaker, fallback: FallbackSpeaker) -> VoiceLoop:
    """Convenience constructor that plugs in the real production stages.

    Kept import-light: only asr is imported here so the text REPL path never
    pays for faster-whisper's startup cost.
    """
    from jarvis.pipeline import asr as asr_module

    return VoiceLoop(
        recorder=lambda cfg: record_until_silence(cfg),
        transcriber=lambda pcm: asr_module.transcribe(pcm),
        brain=lambda text: brain.ask_stream(text),
        speaker=speaker_stream,
        fallback_speaker=fallback,
    )
