"""LLM brain — text in, text out, may call tools.

Phase 0 implements a graceful stub that works with or without an API key so
you can `python -m jarvis` on any machine and see the loop.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from jarvis.settings import settings
from jarvis.tools import registry

log = logging.getLogger(__name__)


class Brain:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._history: list[dict[str, Any]] = [
            {"role": "system", "content": settings.llm.system_prompt}
        ]
        self._init_client()

    def _init_client(self) -> None:
        if not settings.openai_api_key:
            log.warning("OPENAI_API_KEY not set — Brain will run in echo/stub mode.")
            return
        try:
            from openai import OpenAI

            kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.llm.base_url:
                kwargs["base_url"] = settings.llm.base_url
            self._client = OpenAI(**kwargs)
        except Exception as e:  # pragma: no cover
            log.exception("failed to init OpenAI client: %s", e)
            self._client = None

    def ask(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})

        if self._client is None:
            reply = f"(stub) I heard: {user_text}"
            self._history.append({"role": "assistant", "content": reply})
            return reply

        tools_schema = registry.openai_schema()
        for _ in range(4):  # max tool-call hops
            resp = self._client.chat.completions.create(
                model=settings.llm.model,
                messages=self._history,
                temperature=settings.llm.temperature,
                tools=tools_schema or None,
            )
            msg = resp.choices[0].message
            self._history.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                return msg.content or ""

            for call in msg.tool_calls:
                tool = registry.get(call.function.name)
                if tool is None:
                    result = f"unknown tool: {call.function.name}"
                else:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result = str(tool.func(**args))
                    except Exception as e:
                        result = f"tool error: {e}"
                self._history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
        return "(gave up after too many tool hops)"
