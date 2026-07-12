"""Phase 1 entry: a streaming text REPL over brain + tools + adapter.

Later phases replace the ``prompt_toolkit`` input and ``rich`` output with
ASR and TTS while keeping the same loop shape.
"""
from __future__ import annotations

import logging
import textwrap

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


def _banner() -> None:
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


def _handle_slash(cmd: str, memory: Memory, brain: Brain) -> bool:
    """Return True to keep looping, False to exit."""
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


def main() -> None:
    configure_proxy_env()
    setup_logging(settings.log_level)
    _banner()
    memory = Memory(settings.memory.path)
    brain = Brain(memory=memory)
    session: PromptSession[str] = PromptSession()
    prompt = HTML("<ansimagenta><b>you › </b></ansimagenta>")
    try:
        while True:
            try:
                user = session.prompt(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not user:
                continue
            if user.startswith("/"):
                if not _handle_slash(user, memory, brain):
                    break
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
    finally:
        memory.close()
        console.print("[dim]bye.[/dim]")
