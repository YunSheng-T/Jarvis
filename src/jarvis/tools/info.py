"""Read-only info tools: clock, weather, timer.

These are intentionally dependency-light: HTTP calls go through ``httpx`` which
is already vendored via the OpenAI SDK, and timers are backed by an in-process
``threading.Timer`` that fires a desktop notification via the platform adapter.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from jarvis.platform_adapter import get_adapter

from .registry import Tool, registry

log = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HTTP_TIMEOUT = 6.0


def _clock(timezone: str = "") -> str:
    """Return the current local time (optionally for an IANA timezone)."""
    if timezone:
        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise RuntimeError(f"unknown timezone: {timezone!r}") from exc
        now = datetime.now(tz=tz)
        return now.strftime("%Y-%m-%d %H:%M:%S %Z")
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


_WEATHER_CODE = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _geocode(location: str) -> dict[str, Any]:
    resp = httpx.get(
        _GEOCODE_URL,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    results = (resp.json() or {}).get("results") or []
    if not results:
        raise RuntimeError(f"no place matched: {location!r}")
    return results[0]


def _weather(location: str) -> str:
    """Fetch current conditions via Open-Meteo (no API key required)."""
    place = _geocode(location)
    resp = httpx.get(
        _FORECAST_URL,
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    current = (resp.json() or {}).get("current") or {}
    if not current:
        raise RuntimeError("weather service returned no current conditions")

    condition = _WEATHER_CODE.get(int(current.get("weather_code", -1)), "unknown")
    label = ", ".join(
        part
        for part in (place.get("name"), place.get("admin1"), place.get("country_code"))
        if part
    )
    return (
        f"{label}: {condition}, "
        f"{current.get('temperature_2m')}°C, "
        f"humidity {current.get('relative_humidity_2m')}%, "
        f"wind {current.get('wind_speed_10m')} km/h"
    )


class _TimerRegistry:
    """Tracks live timers so a REPL command could inspect them later."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timers: dict[int, threading.Timer] = {}
        self._counter = 0

    def schedule(self, delay: float, on_fire) -> int:  # type: ignore[no-untyped-def]
        with self._lock:
            self._counter += 1
            timer_id = self._counter

        def _fire() -> None:
            try:
                on_fire()
            finally:
                with self._lock:
                    self._timers.pop(timer_id, None)

        timer = threading.Timer(delay, _fire)
        timer.daemon = True
        with self._lock:
            self._timers[timer_id] = timer
        timer.start()
        return timer_id


_TIMERS = _TimerRegistry()


def _format_delay(seconds: float) -> str:
    seconds = int(round(seconds))
    parts: list[str] = []
    for unit, size in (("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{unit}")
    return " ".join(parts) or "0s"


def _timer(seconds: int, message: str = "Timer") -> str:
    if seconds <= 0:
        raise RuntimeError("seconds must be positive")
    adapter = get_adapter()
    fires_at = time.strftime("%H:%M:%S", time.localtime(time.time() + seconds))

    def _on_fire() -> None:
        try:
            adapter.notify("Jarvis timer", message)
        except Exception:  # pragma: no cover — best-effort side effect
            log.exception("timer notification failed")

    timer_id = _TIMERS.schedule(seconds, _on_fire)
    return f"timer #{timer_id} set for {_format_delay(seconds)} (fires ~{fires_at}): {message}"


registry.register(
    Tool(
        name="clock",
        description=(
            "Return the current local time. Optionally pass an IANA timezone "
            "such as 'Asia/Hong_Kong' or 'Europe/London'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Optional IANA timezone name.",
                }
            },
        },
        func=_clock,
    )
)


registry.register(
    Tool(
        name="weather",
        description=(
            "Return current outdoor conditions for a place using Open-Meteo. "
            "Accepts city names in any language, e.g. 'Hong Kong' or '香港'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or place name to look up.",
                }
            },
            "required": ["location"],
        },
        func=_weather,
    )
)


registry.register(
    Tool(
        name="timer",
        description=(
            "Set a one-shot reminder. When it fires, Jarvis shows a desktop "
            "notification with the given message. Duration is in seconds."
        ),
        parameters={
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Delay in seconds before firing.",
                },
                "message": {
                    "type": "string",
                    "description": "Text to show when the timer fires.",
                },
            },
            "required": ["seconds"],
        },
        func=_timer,
    )
)
