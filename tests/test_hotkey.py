from __future__ import annotations

import time

import pytest

from jarvis.pipeline import hotkey as hk


class _Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def on_press(self) -> None:
        self.events.append("press")

    def on_release(self) -> None:
        self.events.append("release")


def _make_listener(debounce_ms: int = 0) -> tuple[hk.BaseListener, _Recorder]:
    recorder = _Recorder()
    listener = hk.BaseListener(recorder.on_press, recorder.on_release, debounce_ms=debounce_ms)
    return listener, recorder


def test_press_then_release_fires_exactly_once() -> None:
    listener, rec = _make_listener()
    listener._deliver_press()
    listener._deliver_press()  # ignored: still down
    listener._deliver_release()
    listener._deliver_release()  # ignored: already up
    assert rec.events == ["press", "release"]


def test_debounce_suppresses_rapid_bounces() -> None:
    listener, rec = _make_listener(debounce_ms=50)
    listener._deliver_press()
    listener._deliver_release()

    # Immediate re-press within debounce should be dropped.
    listener._deliver_press()
    assert rec.events == ["press", "release"]

    time.sleep(0.06)
    listener._deliver_press()
    listener._deliver_release()
    assert rec.events == ["press", "release", "press", "release"]


def test_callback_exceptions_are_logged_not_raised() -> None:
    def raiser() -> None:
        raise RuntimeError("boom")

    listener = hk.BaseListener(raiser, raiser, debounce_ms=0)
    # Should not raise; failures are logged.
    listener._deliver_press()
    listener._deliver_release()


def test_build_listener_reports_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hk.platform, "system", lambda: "FreeBSD")
    with pytest.raises(hk.HotkeyError, match="not implemented"):
        hk.build_listener(lambda: None, lambda: None)
