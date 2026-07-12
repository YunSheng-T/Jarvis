"""Platform adapters isolate OS-specific side effects from business logic.

Business code should only import `get_adapter()` and use the abstract methods
declared in `base.PlatformAdapter`.
"""
from __future__ import annotations

import sys

from .base import PlatformAdapter


def get_adapter() -> PlatformAdapter:
    if sys.platform == "darwin":
        from .macos import MacOSAdapter

        return MacOSAdapter()
    if sys.platform.startswith("linux"):
        from .linux import LinuxAdapter

        return LinuxAdapter()
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


__all__ = ["PlatformAdapter", "get_adapter"]
