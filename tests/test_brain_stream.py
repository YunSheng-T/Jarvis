from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from jarvis.pipeline import brain as brain_module
from jarvis.tools.registry import Registry, Tool


class _FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __iter__(self):
        return iter(self._chunks)


def _delta(content: str | None = None, tool_calls=None):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


def _tool_call_delta(index: int, call_id: str | None, name: str | None, arguments: str):
    fn = SimpleNamespace(name=name, arguments=arguments) if (name or arguments) else None
    return SimpleNamespace(index=index, id=call_id, function=fn)


class _FakeCompletions:
    def __init__(self, streams: list[list[Any]]) -> None:
        self._streams = streams
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any):  # noqa: D401 — matches OpenAI SDK signature
        self.calls.append(kwargs)
        return _FakeStream(self._streams.pop(0))


class _FakeClient:
    def __init__(self, streams: list[list[Any]]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(streams))


@pytest.fixture()
def isolate_registry(monkeypatch: pytest.MonkeyPatch) -> Registry:
    fresh = Registry()
    monkeypatch.setattr(brain_module, "registry", fresh)
    return fresh


def test_ask_stream_yields_incremental_chunks(
    monkeypatch: pytest.MonkeyPatch, isolate_registry: Registry
) -> None:
    monkeypatch.setattr(brain_module.Brain, "_init_client", lambda self: None)
    b = brain_module.Brain()
    b._client = _FakeClient([[_delta("Hel"), _delta("lo"), _delta("!")]])

    chunks = list(b.ask_stream("hi"))

    assert chunks == ["Hel", "lo", "!"]
    assert b._history[-1] == {"role": "assistant", "content": "Hello!"}


def test_ask_stream_runs_tool_call_between_hops(
    monkeypatch: pytest.MonkeyPatch, isolate_registry: Registry
) -> None:
    monkeypatch.setattr(brain_module.Brain, "_init_client", lambda self: None)
    called: list[dict[str, Any]] = []

    def echo(**kwargs: Any) -> str:
        called.append(kwargs)
        return "pong"

    isolate_registry.register(
        Tool(
            name="ping",
            description="",
            parameters={"type": "object", "properties": {}},
            func=echo,
        )
    )

    tool_stream = [
        _delta(tool_calls=[_tool_call_delta(0, "call_1", "ping", "")]),
        _delta(tool_calls=[_tool_call_delta(0, None, None, "{}")]),
    ]
    reply_stream = [_delta("done")]

    b = brain_module.Brain()
    b._client = _FakeClient([tool_stream, reply_stream])

    chunks = list(b.ask_stream("please ping"))

    assert chunks == ["done"]
    assert called == [{}]
    assert any(m.get("role") == "tool" and m.get("content") == "pong" for m in b._history)


def test_ask_stream_stub_mode_returns_placeholder(
    monkeypatch: pytest.MonkeyPatch, isolate_registry: Registry
) -> None:
    monkeypatch.setattr(brain_module.Brain, "_init_client", lambda self: None)
    b = brain_module.Brain()

    chunks = list(b.ask_stream("hello"))

    assert chunks == ["(stub) I heard: hello"]
