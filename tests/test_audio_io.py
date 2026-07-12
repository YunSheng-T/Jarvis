from __future__ import annotations

import pytest

from jarvis.pipeline import audio_io


class _ScriptedVAD:
    """A VAD stub driven by a scripted schedule of ``bool`` values."""

    def __init__(self, schedule: list[bool]) -> None:
        self._schedule = list(schedule)
        self._index = 0

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:  # noqa: ARG002
        if self._index >= len(self._schedule):
            return False
        value = self._schedule[self._index]
        self._index += 1
        return value


def _silence_frame() -> bytes:
    return b"\x00" * audio_io.FRAME_BYTES


def _voice_frame() -> bytes:
    # Arbitrary non-zero payload; content doesn't matter — VAD is scripted.
    return (b"\x10\x20") * audio_io.FRAME_SAMPLES


def test_recorder_captures_utterance_with_pre_roll() -> None:
    cfg = audio_io.RecorderConfig(silence_ms=60, min_voiced_ms=40, pre_roll_ms=40)
    # 5 silent frames, 8 voiced, 4 silent -> ends after 3 silent trailing (silence_ms=60).
    schedule = [False] * 5 + [True] * 8 + [False] * 4
    frames = [_silence_frame()] * 5 + [_voice_frame()] * 8 + [_silence_frame()] * 4

    recorder = audio_io.Recorder(_ScriptedVAD(schedule), cfg)
    for frame in frames:
        if recorder.feed(frame):
            break

    assert recorder.done is True
    frames_in_output = len(recorder.collected()) // audio_io.FRAME_BYTES
    # 2 pre-roll frames + 8 voiced + 3 trailing silence to trigger silence_ms=60ms.
    # pre-roll (2) already includes the 2 voiced frames that triggered collecting,
    # then 6 more voiced + 3 trailing silence = 11 frames.
    assert frames_in_output == 2 + 6 + 3


def test_recorder_rejects_wrong_frame_size() -> None:
    recorder = audio_io.Recorder(_ScriptedVAD([]))
    with pytest.raises(ValueError, match="frame size"):
        recorder.feed(b"\x00" * (audio_io.FRAME_BYTES - 2))


def test_recorder_respects_max_seconds() -> None:
    cfg = audio_io.RecorderConfig(silence_ms=1000, max_seconds=0.1)  # 5 frames * 20ms
    recorder = audio_io.Recorder(_ScriptedVAD([True] * 100), cfg)

    fed = 0
    for _ in range(100):
        fed += 1
        if recorder.feed(_voice_frame()):
            break

    assert recorder.done is True
    assert fed <= 5


def test_frames_of_slices_evenly() -> None:
    payload = b"\x00" * (audio_io.FRAME_BYTES * 3 + 5)
    frames = list(audio_io.frames_of(payload))
    assert len(frames) == 3
    assert all(len(f) == audio_io.FRAME_BYTES for f in frames)


def test_record_until_silence_reports_missing_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_loader(_config):  # type: ignore[no-untyped-def]
        msg = "audio extras missing; install with `uv sync --extra audio`"
        raise audio_io.AudioCaptureError(msg)

    monkeypatch.setattr(audio_io, "_load_backends", fake_loader)

    with pytest.raises(audio_io.AudioCaptureError, match="audio extras missing"):
        audio_io.record_until_silence()
