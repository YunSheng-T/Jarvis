"""Phase 1 entry: a streaming text REPL over brain + tools + adapter.

Later phases replace the ``prompt_toolkit`` input and ``rich`` output with
ASR and TTS while keeping the same loop shape.
"""
from __future__ import annotations

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
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
    llm_is_live = bool(settings.ark_api_key or settings.openai_api_key)
    console.print(
        Panel.fit(
            f"[bold cyan]Jarvis[/bold cyan]  ·  platform=[green]{adapter.name}[/green]"
            f"  ·  model=[green]{settings.llm.model}[/green]"
            f"  ·  llm={'live' if llm_is_live else 'stub'}\n"
            "Type your message. `/quit` to exit.",
            border_style="cyan",
        )
    )


def main() -> None:
    setup_logging(settings.log_level)
    _banner()
    brain = Brain()
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
            if user in {"/quit", "/exit"}:
                break
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
        console.print("[dim]bye.[/dim]")
