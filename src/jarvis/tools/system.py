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
