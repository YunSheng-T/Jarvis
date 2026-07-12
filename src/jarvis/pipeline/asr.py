"""Local speech recognition via faster-whisper.

The transcriber is lazily constructed the first time it is used so importing
this module remains cheap on machines without the ASR extra installed. Model
files land in ``settings.asr.model_dir`` (default
``~/.local/share/jarvis/models/asr``) and are shared across runs.
"""
from __future__ import annotations

import logging
import time
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from jarvis.net import configure_proxy_env
from jarvis.pipeline.audio_io import CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH_BYTES
from jarvis.settings import settings

log = logging.getLogger(__name__)


class ASRError(RuntimeError):
    """Raised when transcription cannot be produced."""


@dataclass(slots=True)
class Transcription:
    text: str
    language: str
    duration_ms: int
    latency_ms: int


def _pcm_to_wav_bytes(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM in a WAV container in memory; faster-whisper accepts this."""
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def _resolve_model_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


class Transcriber:
    """Wraps a :class:`faster_whisper.WhisperModel` with a friendly interface."""

    def __init__(self, model: Any | None = None) -> None:
        self._model: Any | None = model
        self._model_key: tuple[str, str, str] | None = None

    def _ensure_model(self) -> Any:
        configure_proxy_env()
        cfg = settings.asr
        key = (cfg.model, cfg.compute, cfg.model_dir)
        if self._model is not None and self._model_key == key:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:  # pragma: no cover — depends on optional extra
            msg = "faster-whisper is not installed; run `uv sync --extra asr`"
            raise ASRError(msg) from exc

        download_dir = _resolve_model_dir(cfg.model_dir)
        log.info(
            "loading faster-whisper model=%s compute=%s dir=%s",
            cfg.model,
            cfg.compute,
            download_dir,
        )
        self._model = WhisperModel(
            cfg.model,
            device="auto",
            compute_type=cfg.compute,
            download_root=str(download_dir),
        )
        self._model_key = key
        return self._model

    def transcribe(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcription:
        if not pcm:
            raise ASRError("no audio to transcribe")

        model = self._ensure_model()
        cfg = settings.asr
        wav_bytes = _pcm_to_wav_bytes(pcm, sample_rate=sample_rate)

        start = time.monotonic()
        segments, info = model.transcribe(
            BytesIO(wav_bytes),
            language=cfg.language or None,
            initial_prompt=", ".join(cfg.hint_terms) or None,
            vad_filter=False,  # WebRTC VAD already handled endpointing
            beam_size=1,
        )
        text = "".join(segment.text for segment in segments).strip()
        latency_ms = int((time.monotonic() - start) * 1000)
        duration_ms = int(len(pcm) / (sample_rate * SAMPLE_WIDTH_BYTES) * 1000)

        return Transcription(
            text=text,
            language=(info.language or "").lower(),
            duration_ms=duration_ms,
            latency_ms=latency_ms,
        )


_default_transcriber: Transcriber | None = None


def transcribe(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Transcription:
    """Module-level convenience that caches a single transcriber instance."""
    global _default_transcriber
    if _default_transcriber is None:
        _default_transcriber = Transcriber()
    return _default_transcriber.transcribe(pcm, sample_rate=sample_rate)
