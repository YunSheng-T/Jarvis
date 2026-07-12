"""Microphone capture with WebRTC VAD-based endpointing.

Phase 2 uses this module in two shapes:

* :func:`record_until_silence` returns one utterance as a ``bytes`` blob of
  16 kHz mono 16-bit PCM. Recording starts immediately and stops when the
  speaker has been quiet for ``silence_ms`` milliseconds, or when
  ``max_seconds`` elapses.
* :class:`Recorder` is the underlying state machine and is what the tests
  exercise directly, without going anywhere near a real microphone.

The design keeps ``sounddevice`` and ``webrtcvad`` imports lazy so this module
can be imported on machines that do not yet have the ``audio`` extra
installed — for instance to run the text REPL.
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH_BYTES

_VALID_FRAME_MS = {10, 20, 30}


class AudioCaptureError(RuntimeError):
    """Raised when audio capture cannot start."""


@dataclass(slots=True)
class RecorderConfig:
    sample_rate: int = SAMPLE_RATE
    frame_ms: int = FRAME_MS
    silence_ms: int = 400
    max_seconds: float = 15.0
    vad_aggressiveness: int = 2  # 0=lenient, 3=strict
    min_voiced_ms: int = 120  # need this much speech before we start "collecting"
    pre_roll_ms: int = 200  # keep this much audio before the first voiced frame

    def validate(self) -> None:
        if self.frame_ms not in _VALID_FRAME_MS:
            raise ValueError(
                f"frame_ms must be one of {_VALID_FRAME_MS}, got {self.frame_ms}"
            )
        if self.silence_ms <= 0 or self.max_seconds <= 0:
            raise ValueError("silence_ms and max_seconds must be positive")
        if not 0 <= self.vad_aggressiveness <= 3:
            raise ValueError("vad_aggressiveness must be 0..3")


class _VADProtocol:
    """The tiny slice of webrtcvad we actually use, so tests can substitute."""

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:  # pragma: no cover
        raise NotImplementedError


class Recorder:
    """Frame-by-frame VAD state machine.

    The recorder is fed 20 ms frames of 16-bit mono PCM via :meth:`feed`. It
    returns ``True`` once an utterance is complete; the collected PCM is then
    available via :meth:`collected`.
    """

    def __init__(self, vad: _VADProtocol, config: RecorderConfig | None = None) -> None:
        self._vad = vad
        self._cfg = config or RecorderConfig()
        self._cfg.validate()
        frames_per_ms = 1 / self._cfg.frame_ms
        self._silence_frames_needed = int(self._cfg.silence_ms * frames_per_ms)
        self._min_voiced_frames = max(1, int(self._cfg.min_voiced_ms * frames_per_ms))
        self._pre_roll_frames = max(0, int(self._cfg.pre_roll_ms * frames_per_ms))
        self._max_frames = int(self._cfg.max_seconds * 1000 * frames_per_ms)
        self._pre_roll: deque[bytes] = deque(maxlen=self._pre_roll_frames or 1)
        self._collected: list[bytes] = []
        self._voiced_frames = 0
        self._trailing_silence = 0
        self._collecting = False
        self._done = False
        self._frames_seen = 0

    @property
    def done(self) -> bool:
        return self._done

    def collected(self) -> bytes:
        return b"".join(self._collected)

    def feed(self, frame: bytes) -> bool:
        """Feed one PCM frame; return True once the utterance is finished."""
        if self._done:
            return True
        if len(frame) != self._expected_frame_bytes:
            raise ValueError(
                f"frame size {len(frame)} does not match expected "
                f"{self._expected_frame_bytes} bytes"
            )
        self._frames_seen += 1
        is_speech = self._vad.is_speech(frame, self._cfg.sample_rate)

        if not self._collecting:
            self._pre_roll.append(frame)
            if is_speech:
                self._voiced_frames += 1
                if self._voiced_frames >= self._min_voiced_frames:
                    self._start_collecting()
            else:
                self._voiced_frames = 0
        else:
            self._collected.append(frame)
            if is_speech:
                self._trailing_silence = 0
            else:
                self._trailing_silence += 1
                if self._trailing_silence >= self._silence_frames_needed:
                    self._done = True

        if self._frames_seen >= self._max_frames:
            if not self._collecting:
                # Flush pre-roll so short utterances at the buffer edge survive.
                self._collected.extend(self._pre_roll)
            self._done = True

        return self._done

    def _start_collecting(self) -> None:
        self._collecting = True
        self._collected.extend(self._pre_roll)
        self._pre_roll.clear()
        self._trailing_silence = 0

    @property
    def _expected_frame_bytes(self) -> int:
        return int(self._cfg.sample_rate * self._cfg.frame_ms / 1000) * SAMPLE_WIDTH_BYTES


def frames_of(pcm: bytes, frame_bytes: int = FRAME_BYTES) -> Iterator[bytes]:
    """Split raw PCM into frames of the requested size, dropping the tail."""
    for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        yield pcm[i : i + frame_bytes]


def collect_from(
    frames: Iterable[bytes],
    vad: _VADProtocol,
    config: RecorderConfig | None = None,
) -> bytes:
    """Drive the recorder from an iterable of frames (used by tests + tools)."""
    recorder = Recorder(vad, config)
    for frame in frames:
        if recorder.feed(frame):
            break
    return recorder.collected()


def _load_backends(config: RecorderConfig):  # type: ignore[no-untyped-def]
    try:
        import sounddevice as sd  # type: ignore
        import webrtcvad  # type: ignore
    except ImportError as exc:  # pragma: no cover — depends on optional extra
        raise AudioCaptureError(
            "audio extras missing; install with `uv sync --extra audio`"
        ) from exc
    return sd, webrtcvad.Vad(config.vad_aggressiveness)


def record_until_silence(
    config: RecorderConfig | None = None,
    device: str | int | None = None,
) -> bytes:
    """Record one utterance from the default microphone.

    Blocks until the recorder marks the utterance complete. Returns the raw
    16-bit mono PCM at the configured sample rate.
    """
    cfg = config or RecorderConfig()
    cfg.validate()
    sd, vad = _load_backends(cfg)
    recorder = Recorder(vad, cfg)
    frame_samples = int(cfg.sample_rate * cfg.frame_ms / 1000)

    with sd.RawInputStream(
        samplerate=cfg.sample_rate,
        blocksize=frame_samples,
        dtype="int16",
        channels=CHANNELS,
        device=device,
    ) as stream:
        while not recorder.done:
            data, overflowed = stream.read(frame_samples)
            if overflowed:
                log.warning("audio input overflow; frame may be corrupted")
            if recorder.feed(bytes(data)):
                break
    return recorder.collected()
