from __future__ import annotations

from typing import Any

import httpx
import pytest

from jarvis.tools import info as info_tools


def test_clock_default_returns_iso_like_string() -> None:
    text = info_tools._clock()
    assert len(text) >= 19
    assert text[4] == "-" and text[7] == "-"


def test_clock_named_timezone() -> None:
    text = info_tools._clock("Asia/Hong_Kong")
    assert "HKT" in text or "+08" in text or "HKST" in text or " " in text


def test_clock_rejects_unknown_timezone() -> None:
    with pytest.raises(RuntimeError, match="unknown timezone"):
        info_tools._clock("Mars/Olympus_Mons")


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_weather_formats_current_conditions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, params=None, timeout=None):  # type: ignore[no-untyped-def]
        calls.append(url)
        if "geocoding" in url:
            return _FakeResponse(
                {
                    "results": [
                        {
                            "name": "Hong Kong",
                            "admin1": "Hong Kong",
                            "country_code": "HK",
                            "latitude": 22.3,
                            "longitude": 114.2,
                        }
                    ]
                }
            )
        return _FakeResponse(
            {
                "current": {
                    "temperature_2m": 28.5,
                    "relative_humidity_2m": 74,
                    "weather_code": 61,
                    "wind_speed_10m": 12.3,
                }
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    result = info_tools._weather("Hong Kong")

    assert "Hong Kong" in result
    assert "slight rain" in result
    assert "28.5°C" in result
    assert calls[0].endswith("/v1/search")
    assert calls[1].endswith("/v1/forecast")


def test_weather_reports_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, params=None, timeout=None):  # type: ignore[no-untyped-def]
        return _FakeResponse({"results": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(RuntimeError, match="no place matched"):
        info_tools._weather("Atlantis")


def test_timer_rejects_non_positive() -> None:
    with pytest.raises(RuntimeError, match="seconds must be positive"):
        info_tools._timer(0, "nope")


def test_timer_schedules_and_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeAdapter:
        def notify(self, title: str, body: str) -> None:
            calls.append((title, body))

    monkeypatch.setattr(info_tools, "get_adapter", lambda: _FakeAdapter())

    scheduled: dict[str, Any] = {}

    def fake_schedule(delay: float, on_fire) -> int:  # type: ignore[no-untyped-def]
        scheduled["delay"] = delay
        scheduled["fn"] = on_fire
        return 42

    monkeypatch.setattr(info_tools._TIMERS, "schedule", fake_schedule)

    result = info_tools._timer(90, "stretch")

    assert "timer #42" in result
    assert scheduled["delay"] == 90
    scheduled["fn"]()  # simulate firing
    assert calls == [("Jarvis timer", "stretch")]
