"""Built-in tools that touch the OS via the platform adapter."""
from __future__ import annotations

import logging

from jarvis.platform_adapter import get_adapter

from .registry import Tool, registry

log = logging.getLogger(__name__)
_adapter = get_adapter()


def _notify(title: str, body: str) -> str:
    _adapter.notify(title, body)
    return f"notified: {title}"


def _open_app(app: str) -> str:
    _adapter.open_app(app)
    return f"opened: {app}"


def _set_volume(percent: int) -> str:
    _adapter.set_volume(percent)
    return f"volume set to {percent}%"


def _install_app(package: str) -> str:
    return _adapter.install_app(package)


def _play_music(query: str, service: str = "spotify") -> str:
    return _adapter.play_music(query, service)


registry.register(
    Tool(
        name="notify",
        description="Show a short desktop notification to the user.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title", "body"],
        },
        func=_notify,
    )
)

registry.register(
    Tool(
        name="open_app",
        description="Open a desktop application by name (e.g. 'Safari', 'firefox').",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string"}},
            "required": ["app"],
        },
        func=_open_app,
    )
)

registry.register(
    Tool(
        name="set_volume",
        description="Set the system output volume as a percentage 0-100.",
        parameters={
            "type": "object",
            "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["percent"],
        },
        func=_set_volume,
    )
)


registry.register(
    Tool(
        name="install_app",
        description=(
            "Install a desktop application by name using the host's package manager. "
            "On Linux prefers snap and falls back to apt; on macOS uses Homebrew. "
            "May require the user to enter a sudo/admin password in the terminal."
        ),
        parameters={
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "Application name, e.g. 'spotify', 'firefox', 'code'.",
                }
            },
            "required": ["package"],
        },
        func=_install_app,
    )
)


registry.register(
    Tool(
        name="play_music",
        description=(
            "Open a music streaming service (currently Spotify) with a search "
            "query. The user can then pick and play the track. Does NOT yet "
            "start playback automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-form search text, e.g. 'Taylor Swift'.",
                },
                "service": {
                    "type": "string",
                    "enum": ["spotify"],
                    "default": "spotify",
                },
            },
            "required": ["query"],
        },
        func=_play_music,
    )
)
