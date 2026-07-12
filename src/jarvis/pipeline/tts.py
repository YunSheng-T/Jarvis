"""Local text-to-speech via Piper, with a platform-native fallback.

Design goals for Phase 2:

* Streaming-friendly: :func:`speak` accepts an iterator of text chunks (the
  brain streams tokens), buffers them into sentences, synthesizes each
  sentence with Piper, and plays it while the next one is being generated.
* Bilingual sensible defaults: if the sentence looks like Chinese we route it
  to a Chinese voice; otherwise the English voice. Behaviour is off by a
  single ``settings.tts.bilingual`` flag.
* Honest degradation: if Piper isn't installed (no ``tts`` extra) or a voice
  file cannot be loaded, we fall back to the platform adapter's
  ``speak_fallback``. That keeps ``spd-say`` on Linux and ``say`` on macOS
  usable so voice mode never goes fully silent.

Model files are downloaded to ``settings.tts.model_dir`` on first use.
"""
from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any

from jarvis.net import configure_proxy_env
from jarvis.platform_adapter import get_adapter
from jarvis.settings import settings

log = logging.getLogger(__name__)


class TTSError(RuntimeError):
    """Raised for unrecoverable synthesis errors."""


_SENTENCE_END = re.compile(r"(?<=[.!?。！？…\n])\s+")
_CHINESE_CHAR = re.compile(r"[\u3400-\u9fff]")


def detect_language(text: str) -> str:
    """Return ``'zh'`` if the segment is mostly Chinese, else ``'en'``."""
    han = len(_CHINESE_CHAR.findall(text))
    return "zh" if han >= max(2, len(text) // 6) else "en"


def _split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split off complete sentences; return ``(sentences, remainder)``."""
    if not buffer:
        return [], ""
    parts = _SENTENCE_END.split(buffer)
    if buffer[-1] in ".!?。！？…\n":
        return [p.strip() for p in parts if p.strip()], ""
    remainder = parts[-1]
    complete = [p.strip() for p in parts[:-1] if p.strip()]
    return complete, remainder


def stream_sentences(chunks: Iterable[str]) -> Iterator[str]:
    """Buffer streamed text chunks and yield one complete sentence at a time."""
    buffer = ""
    for chunk in chunks:
        if not chunk:
            continue
        buffer += chunk
        sentences, buffer = _split_sentences(buffer)
        yield from sentences
    tail = buffer.strip()
    if tail:
        yield tail


@dataclass(slots=True)
class Utterance:
    """A single synthesised audio chunk ready to be played."""

    pcm: bytes
    sample_rate: int
    channels: int
    sample_width: int
    text: str


def _resolve_model_dir() -> Path:
    path = Path(settings.tts.model_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


class PiperEngine:
    """Loads Piper voices on demand and synthesises text into PCM."""

    def __init__(self) -> None:
        self._voices: dict[str, Any] = {}

    def _load_voice(self, voice_name: str) -> Any:
        cached = self._voices.get(voice_name)
        if cached is not None:
            return cached
        try:
            from piper import PiperVoice  # type: ignore
        except ImportError as exc:  # pragma: no cover — depends on optional extra
            msg = "piper-tts is not installed; run `uv sync --extra tts`"
            raise TTSError(msg) from exc

        configure_proxy_env()
        model_dir = _resolve_model_dir()
        onnx_path = model_dir / f"{voice_name}.onnx"
        if not onnx_path.exists():
            self._download_voice(voice_name, model_dir)
        log.info("loading piper voice %s from %s", voice_name, onnx_path)
        voice = PiperVoice.load(onnx_path)
        self._voices[voice_name] = voice
        return voice

    @staticmethod
    def _download_voice(voice_name: str, model_dir: Path) -> None:
        # Voice URLs follow the format used by the Piper voices repository. If
        # the file is missing at runtime we raise a TTSError; the caller then
        # falls back to the platform's built-in speech engine.
        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except ImportError as exc:  # pragma: no cover
            msg = (
                f"piper voice {voice_name!r} not found at {model_dir}; "
                "install huggingface_hub or place the .onnx and .onnx.json manually"
            )
            raise TTSError(msg) from exc

        # rhasspy/piper-voices layout: <lang>/<region>/<speaker>/<quality>/<file>
        try:
            lang, rest = voice_name.split("_", 1)
            region, speaker_quality = rest.split("-", 1)
            speaker, quality = speaker_quality.rsplit("-", 1)
        except ValueError as exc:
            msg = f"cannot parse piper voice name: {voice_name!r}"
            raise TTSError(msg) from exc

        subdir = f"{lang}/{lang}_{region}/{speaker}/{quality}"
        for filename in (f"{voice_name}.onnx", f"{voice_name}.onnx.json"):
            hf_hub_download(
                repo_id="rhasspy/piper-voices",
                filename=f"{subdir}/{filename}",
                local_dir=str(model_dir),
                local_dir_use_symlinks=False,
            )
            # hf_hub_download stores files under the subdir; move them up.
            downloaded = model_dir / subdir / filename
            target = model_dir / filename
            if downloaded.exists() and not target.exists():
                downloaded.rename(target)

    def synthesize(self, text: str, language: str) -> list[Utterance]:
        voice_name = settings.tts.voice_zh if language == "zh" else settings.tts.voice_en
        voice = self._load_voice(voice_name)
        chunks = list(voice.synthesize(text))
        return [
            Utterance(
                pcm=chunk.audio_int16_bytes,
                sample_rate=int(getattr(chunk, "sample_rate", voice.config.sample_rate)),
                channels=1,
                sample_width=2,
                text=text,
            )
            for chunk in chunks
        ]


def _play_pcm(utterance: Utterance) -> None:
    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore
    except ImportError as exc:  # pragma: no cover
        msg = "sounddevice/numpy missing; install with `uv sync --extra tts`"
        raise TTSError(msg) from exc

    samples = np.frombuffer(utterance.pcm, dtype=np.int16)
    sd.play(samples, samplerate=utterance.sample_rate, blocking=True)


class Speaker:
    """High-level façade the REPL/voice loop uses.

    Prefers Piper; on synthesis failure, falls back once to the platform
    adapter's built-in speech and logs the reason so users notice.
    """

    def __init__(self, engine: PiperEngine | None = None) -> None:
        self._engine = engine or PiperEngine()
        self._adapter = get_adapter()

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        language = detect_language(text) if settings.tts.bilingual else "en"
        try:
            utterances = self._engine.synthesize(text, language)
        except TTSError as exc:
            log.warning("piper failed (%s); falling back to system TTS", exc)
            self._adapter.speak_fallback(text)
            return
        for utterance in utterances:
            _play_pcm(utterance)

    def stream(self, chunks: Iterable[str]) -> None:
        """Consume streaming text and speak sentence-by-sentence.

        Synthesis runs on the main thread; playback of one sentence overlaps
        with synthesis of the next through a small queue so the user hears
        the reply as soon as the first sentence is ready.
        """
        queue: Queue[Utterance | None] = Queue(maxsize=4)

        def _worker() -> None:
            while True:
                item = queue.get()
                if item is None:
                    return
                try:
                    _play_pcm(item)
                except Exception:  # noqa: BLE001
                    log.exception("audio playback failed")

        player = threading.Thread(target=_worker, daemon=True)
        player.start()

        try:
            for sentence in stream_sentences(chunks):
                language = detect_language(sentence) if settings.tts.bilingual else "en"
                try:
                    utterances = self._engine.synthesize(sentence, language)
                except TTSError as exc:
                    log.warning("piper failed on %r (%s); using fallback", sentence, exc)
                    self._adapter.speak_fallback(sentence)
                    continue
                for utterance in utterances:
                    queue.put(utterance)
        finally:
            queue.put(None)
            player.join(timeout=5.0)


_default_speaker: Speaker | None = None


def speak(chunks: Iterable[str]) -> None:
    """Module-level helper for the streaming case."""
    global _default_speaker
    if _default_speaker is None:
        _default_speaker = Speaker()
    _default_speaker.stream(chunks)
