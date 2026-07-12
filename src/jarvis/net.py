"""Small networking hygiene helpers used across the app.

Currently: normalise legacy ``socks://`` proxy environment variables to the
``socks5://`` scheme that httpx (and therefore openai + huggingface_hub)
require. Call :func:`configure_proxy_env` once at process start so every
client — Brain, faster-whisper's downloader, TTS voice fetcher, etc. — sees
a consistent proxy configuration.
"""
from __future__ import annotations

import os

_PROXY_VARS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
)

_configured = False


def configure_proxy_env() -> None:
    global _configured
    if _configured:
        return
    for name in _PROXY_VARS:
        value = os.environ.get(name)
        if value and value.startswith("socks://"):
            os.environ[name] = f"socks5://{value.removeprefix('socks://')}"
    _configured = True
