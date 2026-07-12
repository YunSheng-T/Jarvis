"""Phase 0 entry: a text REPL that exercises the brain + tools + adapter loop.

Later phases replace `input()` / `print()` with ASR/TTS while keeping the loop.
"""
from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel

from jarvis.logging_setup import setup_logging
from jarvis.pipeline.brain import Brain
from jarvis.platform_adapter import get_adapter
from jarvis.settings import settings

log = logging.getLogger(__name__)
console = Console()


def _banner() -> None:
    adapter = get_adapter()
    console.print(
        Panel.fit(
            f"[bold cyan]Jarvis[/bold cyan]  ·  platform=[green]{adapter.name}[/green]"
            f"  ·  model=[green]{settings.llm.model}[/green]"
            f"  ·  llm={'live' if settings.openai_api_key else 'stub'}\n"
            "Type your message. `/quit` to exit.",
            border_style="cyan",
        )
    )


def main() -> None:
    setup_logging(settings.log_level)
    _banner()
    brain = Brain()
    try:
        while True:
            try:
                user = console.input("[bold magenta]you › [/bold magenta]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not user:
                continue
            if user in {"/quit", "/exit"}:
                break
            reply = brain.ask(user)
            console.print(f"[bold cyan]jarvis ›[/bold cyan] {reply}")
    finally:
        console.print("[dim]bye.[/dim]")
