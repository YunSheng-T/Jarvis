"""LLM brain — text in, text out, may call tools.

Phase 0 implements a graceful stub that works with or without an API key so
you can `python -m jarvis` on any machine and see the loop. Phase 1 adds
streaming: :meth:`Brain.ask_stream` yields text chunks so the REPL can render
tokens as they arrive.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from jarvis.memory import Memory
from jarvis.net import configure_proxy_env
from jarvis.settings import settings
from jarvis.tools import registry

log = logging.getLogger(__name__)

_MAX_TOOL_HOPS = 4


class Brain:
    def __init__(self, memory: Memory | None = None) -> None:
        self._client: Any | None = None
        self._memory = memory
        self._history: list[dict[str, Any]] = self._bootstrap_history()
        self._init_client()

    def _bootstrap_history(self) -> list[dict[str, Any]]:
        system = {"role": "system", "content": settings.llm.system_prompt}
        if self._memory is None:
            return [system]
        stored = self._memory.load()
        if stored and stored[0].get("role") == "system":
            stored[0] = system  # keep the newest system prompt on rehydrate
            return stored
        # First run in this session: persist the system prompt so /history and
        # future restarts see a consistent starting point.
        self._memory.append(system)
        return [system]

    def reset_history(self) -> None:
        """Drop the working context and, when persistent, start a new session."""
        if self._memory is not None:
            self._memory.reset()
        self._history = self._bootstrap_history()

    def _init_client(self) -> None:
        # The OpenAI Python SDK also supports providers implementing its API,
        # including Volcano Engine Ark. Prefer the provider-specific key when set.
        api_key = settings.ark_api_key or settings.openai_api_key
        if not api_key:
            log.warning("No LLM API key set — Brain will run in echo/stub mode.")
            return
        try:
            from openai import OpenAI

            configure_proxy_env()
            kwargs: dict[str, Any] = {"api_key": api_key}
            if settings.llm.base_url:
                kwargs["base_url"] = settings.llm.base_url
            self._client = OpenAI(**kwargs)
        except Exception as e:  # pragma: no cover
            log.exception("failed to init OpenAI client: %s", e)
            self._client = None

    def ask(self, user_text: str) -> str:
        """Non-streaming convenience wrapper: collect the streamed chunks."""
        return "".join(self.ask_stream(user_text))

    def ask_stream(self, user_text: str) -> Iterator[str]:
        """Yield reply text chunks as they arrive from the model.

        Tool calls are executed transparently between streaming hops; the caller
        only ever sees user-facing assistant text. When no API key is configured,
        a single stub chunk is yielded so the REPL remains usable.
        """
        user_msg = {"role": "user", "content": user_text}
        self._history.append(user_msg)
        self._persist(user_msg)

        if self._client is None:
            reply = f"(stub) I heard: {user_text}"
            stub_msg = {"role": "assistant", "content": reply}
            self._history.append(stub_msg)
            self._persist(stub_msg)
            yield reply
            return

        tools_schema = registry.openai_schema()
        for _ in range(_MAX_TOOL_HOPS):
            content, tool_calls = yield from self._stream_once(tools_schema)
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if content:
                assistant_msg["content"] = content
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"],
                        },
                    }
                    for call in tool_calls
                ]
            self._history.append(assistant_msg)
            self._persist(assistant_msg)

            if not tool_calls:
                return

            for call in tool_calls:
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": _run_tool(call["name"], call["arguments"]),
                }
                self._history.append(tool_msg)
                self._persist(tool_msg)

        yield "\n(gave up after too many tool hops)"

    def _stream_once(
        self, tools_schema: list[dict[str, Any]]
    ) -> Iterator[str]:
        """Stream a single model turn.

        Yields user-visible content chunks as they arrive, and returns
        ``(full_content, tool_calls)`` via ``StopIteration.value`` so
        :meth:`ask_stream` can decide whether to run tools and loop.
        """
        stream = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=settings.llm.model,
            messages=self._history,
            temperature=settings.llm.temperature,
            tools=tools_schema or None,
            stream=True,
        )

        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, str]] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                content_parts.append(piece)
                yield piece
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_calls.setdefault(
                    tc.index, {"id": "", "name": "", "arguments": ""}
                )
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments

        ordered = [tool_calls[i] for i in sorted(tool_calls)]
        return "".join(content_parts), ordered


    def _persist(self, message: dict[str, Any]) -> None:
        if self._memory is not None:
            self._memory.append(message)


def _run_tool(name: str, arguments: str) -> str:
    tool = registry.get(name)
    if tool is None:
        return f"unknown tool: {name}"
    try:
        args = json.loads(arguments or "{}")
        return str(tool.func(**args))
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
        return f"tool error: {exc}"
