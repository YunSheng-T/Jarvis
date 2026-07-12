"""Global push-to-talk hotkey listener.

Design principles:

* The listener is a small state machine that emits ``on_press`` and
  ``on_release`` callbacks; it does not know about the voice loop. That lets
  us unit-test it with synthetic events and swap the backend per-platform.
* On Linux we read directly from evdev, so the hotkey works globally
  regardless of which window is focused and does not depend on X11/Wayland.
* On macOS we defer to :mod:`pynput`, which asks the user to grant
  Accessibility permission the first time it runs.
* Missing dependencies do not crash the app; the listener reports a clear
  reason and the caller can fall back to a keyboard-driven mode.
"""
from __future__ import annotations

import logging
import platform
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


class HotkeyError(RuntimeError):
    """Raised when a hotkey listener cannot be started."""


@dataclass(slots=True)
class HotkeyConfig:
    """Preferences shared across backends."""

    linux_key: str = "KEY_RIGHTCTRL"
    macos_key: str = "<ctrl>+`"
    debounce_ms: int = 60


OnPress = Callable[[], None]
OnRelease = Callable[[], None]


class BaseListener:
    """Common state-machine used by every backend.

    Callers only see ``on_press`` and ``on_release`` — each call means "start
    of a fresh utterance" or "stop the current one". Repeat key-repeat events
    from the kernel are collapsed so a held key does not fire dozens of press
    callbacks per second.
    """

    def __init__(
        self,
        on_press: OnPress,
        on_release: OnRelease,
        debounce_ms: int = 60,
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._debounce = max(0, debounce_ms) / 1000.0
        self._pressed = False
        self._last_transition = 0.0

    def _deliver_press(self) -> None:
        now = time.monotonic()
        if self._pressed:
            return
        if now - self._last_transition < self._debounce:
            return
        self._pressed = True
        self._last_transition = now
        try:
            self._on_press()
        except Exception:  # noqa: BLE001
            log.exception("on_press callback failed")

    def _deliver_release(self) -> None:
        now = time.monotonic()
        if not self._pressed:
            return
        self._pressed = False
        self._last_transition = now
        try:
            self._on_release()
        except Exception:  # noqa: BLE001
            log.exception("on_release callback failed")


class LinuxEvdevListener(BaseListener):
    """Linux backend: listen on all keyboard input devices via evdev.

    Requires read access to ``/dev/input/event*``. If access is denied the
    listener raises :class:`HotkeyError` with the exact ``usermod`` command
    the user needs to run once.
    """

    def __init__(
        self,
        on_press: OnPress,
        on_release: OnRelease,
        key_name: str = "KEY_RIGHTCTRL",
        debounce_ms: int = 60,
    ) -> None:
        super().__init__(on_press, on_release, debounce_ms=debounce_ms)
        self._key_name = key_name
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            import evdev  # type: ignore
        except ImportError as exc:  # pragma: no cover
            msg = "evdev is not installed; run `uv sync --extra linux`"
            raise HotkeyError(msg) from exc

        try:
            key_code = int(evdev.ecodes.ecodes[self._key_name])
        except KeyError as exc:  # pragma: no cover — misconfigured key name
            msg = f"unknown key name: {self._key_name!r}"
            raise HotkeyError(msg) from exc

        keyboards = _discover_keyboards(evdev)
        if not keyboards:
            msg = (
                "no keyboard input devices found. If you are on Linux, ensure "
                "your user can read /dev/input/event*. Try: "
                "`sudo usermod -aG input $USER` then log out and back in."
            )
            raise HotkeyError(msg)

        for device in keyboards:
            thread = threading.Thread(
                target=self._pump,
                args=(device, key_code, evdev),
                daemon=True,
                name=f"jarvis-hotkey-{device.path.split('/')[-1]}",
            )
            thread.start()
            self._threads.append(thread)
        log.info(
            "hotkey listening on %d device(s) for %s",
            len(self._threads),
            self._key_name,
        )

    def stop(self) -> None:
        self._stop.set()

    def _pump(self, device: Any, key_code: int, evdev: Any) -> None:
        try:
            for event in device.read_loop():
                if self._stop.is_set():
                    return
                if event.type != evdev.ecodes.EV_KEY or event.code != key_code:
                    continue
                # evdev key values: 0=up, 1=down, 2=autorepeat.
                if event.value == 1:
                    self._deliver_press()
                elif event.value == 0:
                    self._deliver_release()
        except OSError as exc:
            if exc.errno == 13:  # PermissionError
                log.error(
                    "no permission to read %s. Add your user to the 'input' "
                    "group: sudo usermod -aG input $USER, then log out/in.",
                    device.path,
                )
            else:  # pragma: no cover
                log.exception("hotkey read loop failed on %s", device.path)


def _discover_keyboards(evdev: Any) -> list[Any]:
    keyboards: list[Any] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except PermissionError:
            continue
        capabilities = device.capabilities().get(evdev.ecodes.EV_KEY, [])
        # A "real" keyboard is one that reports the letter A.
        if evdev.ecodes.KEY_A in capabilities:
            keyboards.append(device)
    return keyboards


class MacHotkeyListener(BaseListener):
    """macOS backend using :mod:`pynput`. Requires Accessibility permission."""

    def __init__(
        self,
        on_press: OnPress,
        on_release: OnRelease,
        combination: str = "<ctrl>+`",
        debounce_ms: int = 60,
    ) -> None:
        super().__init__(on_press, on_release, debounce_ms=debounce_ms)
        self._combination = combination
        self._listener: Any | None = None

    def start(self) -> None:
        try:
            from pynput import keyboard  # type: ignore
        except ImportError as exc:  # pragma: no cover
            msg = "pynput is not installed; run `uv sync --extra darwin`"
            raise HotkeyError(msg) from exc

        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(self._combination),
            self._deliver_press,
        )

        def _for_canonical(fn):  # type: ignore[no-untyped-def]
            return lambda k: fn(self._listener.canonical(k))  # type: ignore[union-attr]

        self._listener = keyboard.Listener(
            on_press=_for_canonical(hotkey.press),
            on_release=self._on_release_wrapper(hotkey, _for_canonical),
        )
        self._listener.start()
        log.info("hotkey listening for %s", self._combination)

    def _on_release_wrapper(self, hotkey: Any, wrap: Callable[[Any], Any]) -> Any:
        def handler(key: Any) -> None:
            wrap(hotkey.release)(key)
            self._deliver_release()

        return handler

    def stop(self) -> None:  # pragma: no cover — depends on pynput
        if self._listener is not None:
            self._listener.stop()


def build_listener(
    on_press: OnPress,
    on_release: OnRelease,
    config: HotkeyConfig | None = None,
) -> BaseListener:
    """Return the listener appropriate for the current platform."""
    cfg = config or HotkeyConfig()
    system = platform.system()
    if system == "Linux":
        return LinuxEvdevListener(
            on_press,
            on_release,
            key_name=cfg.linux_key,
            debounce_ms=cfg.debounce_ms,
        )
    if system == "Darwin":
        return MacHotkeyListener(
            on_press,
            on_release,
            combination=cfg.macos_key,
            debounce_ms=cfg.debounce_ms,
        )
    msg = f"hotkey backend for {system!r} is not implemented"
    raise HotkeyError(msg)
