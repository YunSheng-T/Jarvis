from __future__ import annotations

import wave
from io import BytesIO
from typing import Any

import pytest

from jarvis.pipeline import asr as asr_module
from jarvis.pipeline.audio_io import FRAME_BYTES


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeInfo:
    def __init__(self, language: str) -> None:
        self.language = language


class _FakeWhisperModel:
    def __init__(
        self, *, script: list[str], language: str = "en", record: list[Any] | None = None
    ) -> None:
        self._script = script
        self._language = language
        self._record = record if record is not None else []

    def transcribe(self, audio, **kwargs: Any):  # noqa: ANN001
        self._record.append({"audio": audio, "kwargs": kwargs})
        return [_FakeSegment(text=self._script.pop(0))], _FakeInfo(self._language)


def _pcm(nbytes: int) -> bytes:
    return b"\x01\x02" * (nbytes // 2)


def test_pcm_to_wav_round_trip() -> None:
    payload = _pcm(FRAME_BYTES * 3)
    wav_bytes = asr_module._pcm_to_wav_bytes(payload, sample_rate=16000)

    with wave.open(BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.readframes(wav.getnframes()) == payload


def test_transcribe_uses_hint_terms_and_returns_metadata() -> None:
    calls: list[dict[str, Any]] = []
    fake_model = _FakeWhisperModel(script=["hello world"], language="EN", record=calls)
    transcriber = asr_module.Transcriber(model=fake_model)
    transcriber._model_key = (
        asr_module.settings.asr.model,
        asr_module.settings.asr.compute,
        asr_module.settings.asr.model_dir,
    )

    original_hints = asr_module.settings.asr.hint_terms
    asr_module.settings.asr.hint_terms = ["Spotify", "Jarvis"]
    try:
        result = transcriber.transcribe(_pcm(FRAME_BYTES * 4), sample_rate=16000)
    finally:
        asr_module.settings.asr.hint_terms = original_hints

    assert result.text == "hello world"
    assert result.language == "en"
    assert result.duration_ms > 0
    assert result.latency_ms >= 0
    assert calls[0]["kwargs"]["initial_prompt"] == "Spotify, Jarvis"
    assert calls[0]["kwargs"]["vad_filter"] is False


def test_transcribe_rejects_empty_pcm() -> None:
    transcriber = asr_module.Transcriber(
        model=_FakeWhisperModel(script=["should not run"])
    )
    with pytest.raises(asr_module.ASRError, match="no audio"):
        transcriber.transcribe(b"")


def test_transcribe_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    transcriber = asr_module.Transcriber()

    def raise_missing() -> Any:
        msg = "faster-whisper is not installed; run `uv sync --extra asr`"
        raise asr_module.ASRError(msg)

    monkeypatch.setattr(transcriber, "_ensure_model", raise_missing)
    with pytest.raises(asr_module.ASRError, match="faster-whisper"):
        transcriber.transcribe(_pcm(FRAME_BYTES))
