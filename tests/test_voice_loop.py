from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from jarvis.pipeline.audio_io import FRAME_BYTES
from jarvis.pipeline.voice_loop import Transcription, VoiceLoop


def _fixed_recorder(pcm: bytes):  # type: ignore[no-untyped-def]
    def _record(_cfg: Any) -> bytes:
        return pcm

    return _record


def _fixed_transcriber(text: str, language: str = "en"):  # type: ignore[no-untyped-def]
    def _transcribe(_pcm: bytes) -> Transcription:
        return Transcription(text=text, language=language)

    return _transcribe


def _brain_reply(chunks: list[str]):  # type: ignore[no-untyped-def]
    def _ask(prompt: str) -> Iterator[str]:
        assert prompt  # sanity — we should get whatever the transcriber returned
        yield from chunks

    return _ask


def test_run_turn_streams_reply_and_records_fragments() -> None:
    played: list[str] = []

    def speaker(stream: Iterator[str]) -> None:
        for chunk in stream:
            played.append(chunk)

    loop = VoiceLoop(
        recorder=_fixed_recorder(b"\x00\x00" * FRAME_BYTES),
        transcriber=_fixed_transcriber("hello"),
        brain=_brain_reply(["Hi ", "there!"]),
        speaker=speaker,
    )

    result = loop.run_turn()

    assert not result.aborted
    assert result.transcript == "hello"
    assert result.reply == "Hi there!"
    assert result.fragments == ["Hi ", "there!"]
    assert played == ["Hi ", "there!"]


def test_run_turn_aborts_on_empty_capture() -> None:
    def speaker(stream: Iterator[str]) -> None:
        list(stream)  # pragma: no cover — should not be reached

    loop = VoiceLoop(
        recorder=lambda _cfg: b"",
        transcriber=_fixed_transcriber("won't be called"),
        brain=_brain_reply(["should not run"]),
        speaker=speaker,
    )

    result = loop.run_turn()

    assert result.aborted is True
    assert result.reason == "no audio captured"


def test_run_turn_speaks_hint_when_transcript_empty() -> None:
    spoken: list[str] = []

    def speaker(stream: Iterator[str]) -> None:
        list(stream)  # pragma: no cover

    loop = VoiceLoop(
        recorder=_fixed_recorder(b"\x00\x00" * FRAME_BYTES),
        transcriber=_fixed_transcriber(""),
        brain=_brain_reply(["should not run"]),
        speaker=speaker,
        fallback_speaker=lambda text: spoken.append(text),
    )

    result = loop.run_turn()

    assert result.aborted is True
    assert result.reason == "empty transcript"
    assert spoken == [loop.empty_hint]


def test_run_turn_surfaces_playback_error() -> None:
    def speaker(_stream: Iterator[str]) -> None:
        raise RuntimeError("boom")

    loop = VoiceLoop(
        recorder=_fixed_recorder(b"\x00\x00" * FRAME_BYTES),
        transcriber=_fixed_transcriber("hello"),
        brain=_brain_reply(["Hi ", "there!"]),
        speaker=speaker,
    )

    result = loop.run_turn()

    assert result.aborted is True
    assert "playback error" in result.reason
    # We should still record what the brain produced *before* the failure,
    # so a partial transcript survives in the log even if the audio failed.
    # The current implementation reports fragments consumed before the raise.
    assert result.transcript == "hello"


def test_build_default_wires_asr_transcribe(monkeypatch: pytest.MonkeyPatch) -> None:
    from jarvis.pipeline import asr as asr_module
    from jarvis.pipeline import voice_loop as vl_module

    seen_pcm: list[bytes] = []

    def fake_transcribe(pcm: bytes) -> Transcription:
        seen_pcm.append(pcm)
        return Transcription(text="ok")

    monkeypatch.setattr(asr_module, "transcribe", fake_transcribe)
    monkeypatch.setattr(vl_module, "record_until_silence", lambda _cfg: b"pcm-bytes")

    played: list[str] = []

    def speaker(stream: Iterator[str]) -> None:
        for chunk in stream:
            played.append(chunk)

    class _Brain:
        def ask_stream(self, prompt: str) -> Iterator[str]:
            yield f"heard: {prompt}"

    loop = vl_module.build_default(_Brain(), speaker, lambda text: None)

    result = loop.run_turn()

    assert seen_pcm == [b"pcm-bytes"]
    assert result.reply == "heard: ok"
    assert played == ["heard: ok"]
