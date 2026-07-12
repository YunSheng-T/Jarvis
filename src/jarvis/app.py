"""Entry point for both the text REPL and the push-to-talk voice mode.

Text mode (default): ``python -m jarvis`` — streaming REPL over
prompt_toolkit + rich, backed by the same Brain + Memory as before.

Voice mode: ``python -m jarvis --voice`` — hold the configured hotkey
(default Right Ctrl on Linux, Ctrl+` on macOS) to speak; release to let
Jarvis transcribe, reply and speak back.
"""
from __future__ import annotations

import argparse
import logging
import textwrap
import threading

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.panel import Panel

from jarvis.logging_setup import setup_logging
from jarvis.memory import Memory
from jarvis.net import configure_proxy_env
from jarvis.pipeline.brain import Brain
from jarvis.platform_adapter import get_adapter
from jarvis.settings import settings
from jarvis.tools import registry

log = logging.getLogger(__name__)
console = Console()

_HELP = textwrap.dedent(
    """\
    Available commands:
      /help              Show this message.
      /history [N]       Show the last N user/assistant turns (default 10).
      /tools             List tools currently exposed to the model.
      /reset             Forget the current conversation and start a new session.
      /quit, /exit       Exit Jarvis.
    """
)


def _text_banner() -> None:
    adapter = get_adapter()
    llm_is_live = bool(settings.ark_api_key or settings.openai_api_key)
    console.print(
        Panel.fit(
            f"[bold cyan]Jarvis[/bold cyan]  ·  platform=[green]{adapter.name}[/green]"
            f"  ·  model=[green]{settings.llm.model}[/green]"
            f"  ·  llm={'live' if llm_is_live else 'stub'}\n"
            "Type your message. `/help` for commands.",
            border_style="cyan",
        )
    )


def _voice_banner(hotkey_label: str) -> None:
    adapter = get_adapter()
    llm_is_live = bool(settings.ark_api_key or settings.openai_api_key)
    console.print(
        Panel.fit(
            f"[bold cyan]Jarvis · voice mode[/bold cyan]  ·  "
            f"platform=[green]{adapter.name}[/green]  ·  "
            f"model=[green]{settings.llm.model}[/green]  ·  "
            f"llm={'live' if llm_is_live else 'stub'}\n"
            f"Hold [bold]{hotkey_label}[/bold] to speak, release to send.  "
            "Ctrl+C to exit.",
            border_style="cyan",
        )
    )


def _handle_slash(cmd: str, memory: Memory, brain: Brain) -> bool:
    parts = cmd.split()
    head = parts[0]
    if head in {"/quit", "/exit"}:
        return False
    if head == "/help":
        console.print(_HELP)
        return True
    if head == "/tools":
        tools = registry.all()
        if not tools:
            console.print("[dim]no tools registered[/dim]")
        else:
            for tool in tools:
                console.print(f"[bold]{tool.name}[/bold] — {tool.description}")
        return True
    if head == "/reset":
        brain.reset_history()
        console.print(
            f"[dim]conversation reset. new session id = {memory.session_id}[/dim]"
        )
        return True
    if head == "/history":
        limit = settings.memory.history_display_limit
        if len(parts) > 1:
            try:
                limit = max(1, int(parts[1]))
            except ValueError:
                console.print("[red]usage: /history [N][/red]")
                return True
        turns = memory.visible_history(limit=limit)
        if not turns:
            console.print("[dim](no conversation yet in this session)[/dim]")
            return True
        for msg in turns:
            role = msg.get("role", "?")
            content = msg.get("content") or ""
            colour = "magenta" if role == "user" else "cyan"
            console.print(f"[{colour}]{role} ›[/{colour}] {content}")
        return True
    console.print(f"[red]unknown command: {head}[/red]  (try /help)")
    return True


def _run_text_repl(memory: Memory, brain: Brain) -> None:
    _text_banner()
    session: PromptSession[str] = PromptSession()
    prompt = HTML("<ansimagenta><b>you › </b></ansimagenta>")
    while True:
        try:
            user = session.prompt(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not user:
            continue
        if user.startswith("/"):
            if not _handle_slash(user, memory, brain):
                return
            continue
        console.print("[bold cyan]jarvis ›[/bold cyan] ", end="")
        any_chunk = False
        for chunk in brain.ask_stream(user):
            if not chunk:
                continue
            any_chunk = True
            console.out(chunk, end="", highlight=False)
        if not any_chunk:
            console.out("(no reply)", end="", highlight=False)
        console.print()


def _run_voice_mode(memory: Memory, brain: Brain) -> None:
    from jarvis.pipeline import hotkey as hk
    from jarvis.pipeline import tts as tts_module
    from jarvis.pipeline import voice_loop as vl_module
    from jarvis.pipeline.audio_io import (
        CHANNELS,
        FRAME_SAMPLES,
        SAMPLE_RATE,
        RecorderConfig,
    )

    adapter = get_adapter()
    speaker = tts_module.Speaker()

    def speak_stream(chunks):  # type: ignore[no-untyped-def]
        speaker.stream(chunks)

    def fallback_say(text: str) -> None:
        try:
            adapter.speak_fallback(text)
        except Exception:  # noqa: BLE001
            log.exception("fallback speak failed")

    # Recorder driven by the hotkey rather than by VAD; we start when the key
    # goes down and stop the moment it comes back up so the user has full
    # control over utterance boundaries.
    recording = threading.Event()
    frames: list[bytes] = []
    frames_lock = threading.Lock()

    def start_recording() -> None:
        with frames_lock:
            frames.clear()
        recording.set()
        console.print("[dim]listening…[/dim]")

    def stop_recording() -> None:
        recording.clear()

    def capture(_cfg: RecorderConfig) -> bytes:
        # Wait until the hotkey pushes us into recording state, then stream
        # frames from the microphone until it flips back off.
        recording.wait()
        try:
            import sounddevice as sd  # type: ignore
        except ImportError as exc:  # pragma: no cover
            log.error("sounddevice missing: %s", exc)
            return b""

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SAMPLES,
            dtype="int16",
            channels=CHANNELS,
        ) as stream:
            while recording.is_set():
                data, overflowed = stream.read(FRAME_SAMPLES)
                if overflowed:
                    log.warning("audio input overflow during capture")
                with frames_lock:
                    frames.append(bytes(data))
        with frames_lock:
            return b"".join(frames)

    loop = vl_module.VoiceLoop(
        recorder=capture,
        transcriber=lambda pcm: _lazy_transcribe(pcm),
        brain=lambda text: brain.ask_stream(text),
        speaker=speak_stream,
        fallback_speaker=fallback_say,
    )

    turn_lock = threading.Lock()

    def run_turn_async() -> None:
        # Only one turn at a time — if the user taps the key while we're still
        # replying, ignore the second press.
        if not turn_lock.acquire(blocking=False):
            console.print("[dim](busy replying; press again after)[/dim]")
            return
        try:
            result = loop.run_turn()
            _render_voice_result(result)
        finally:
            turn_lock.release()

    def on_release() -> None:
        stop_recording()

    def on_press() -> None:
        if turn_lock.locked():
            return
        start_recording()
        threading.Thread(target=run_turn_async, daemon=True).start()

    cfg = hk.HotkeyConfig()
    label = cfg.linux_key if adapter.name == "linux" else cfg.macos_key
    _voice_banner(label)

    try:
        listener = hk.build_listener(on_press, on_release, cfg)
        listener.start()
    except hk.HotkeyError as exc:
        console.print(f"[red]hotkey unavailable: {exc}[/red]")
        console.print("[dim]falling back to text REPL[/dim]")
        _run_text_repl(memory, brain)
        return

    try:
        threading.Event().wait()  # sleep forever; hotkey callbacks drive work
    except KeyboardInterrupt:
        console.print()


def _lazy_transcribe(pcm: bytes):  # type: ignore[no-untyped-def]
    from jarvis.pipeline import asr as asr_module

    return asr_module.transcribe(pcm)


def _render_voice_result(result) -> None:  # type: ignore[no-untyped-def]
    if result.aborted:
        console.print(f"[yellow]· {result.reason}[/yellow]")
        return
    console.print(f"[magenta]you ›[/magenta] {result.transcript}")
    console.print(f"[cyan]jarvis ›[/cyan] {result.reply}")


def _parse_argv(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jarvis", description="Jarvis assistant entry point"
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable push-to-talk voice mode instead of the text REPL.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    configure_proxy_env()
    setup_logging(settings.log_level)
    args = _parse_argv(argv)

    memory = Memory(settings.memory.path)
    brain = Brain(memory=memory)
    try:
        if args.voice:
            _run_voice_mode(memory, brain)
        else:
            _run_text_repl(memory, brain)
    finally:
        memory.close()
        console.print("[dim]bye.[/dim]")
