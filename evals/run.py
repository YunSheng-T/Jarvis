"""Replay a fixed set of prompts and assert the model called the right tools.

Usage:
    uv run python -m evals.run                 # run every case in cases.json
    uv run python -m evals.run --file X.json   # custom suite
    uv run python -m evals.run --only weather  # subset by name substring

Every tool call is intercepted before it reaches the real function so this
harness never actually opens apps, changes volume, sends notifications, or
hits the network. Exit code is non-zero if any case fails, so this can be
wired into CI as a smoke gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.memory import Memory
from jarvis.pipeline.brain import Brain
from jarvis.tools import registry
from jarvis.tools.registry import Tool

DEFAULT_CASES = Path(__file__).with_name("cases.json")


@dataclass
class Case:
    name: str
    prompt: str
    expect_tools: list[str]
    expect_contains: list[str] = field(default_factory=list)


@dataclass
class Result:
    case: Case
    called: list[str]
    reply: str
    ok: bool
    reason: str = ""


def _load(path: Path) -> list[Case]:
    payload = json.loads(path.read_text())
    return [
        Case(
            name=item["name"],
            prompt=item["prompt"],
            expect_tools=list(item.get("expect_tools", [])),
            expect_contains=list(item.get("expect_contains", [])),
        )
        for item in payload
    ]


def _install_probes(recorded: list[str]) -> None:
    """Replace each registered tool's func with a recording stub."""
    for tool in registry.all():
        name = tool.name

        def _stub(_name: str = name, **kwargs: Any) -> str:
            recorded.append(_name)
            return f"[eval] {_name} called with {kwargs}"

        registry.register(
            Tool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                func=_stub,
            )
        )


def _run_case(case: Case) -> Result:
    called: list[str] = []
    _install_probes(called)
    brain = Brain(memory=Memory(":memory:"))
    reply = brain.ask(case.prompt)

    expected = list(case.expect_tools)
    reason = ""
    ok = True

    for name in expected:
        if name not in called:
            ok = False
            reason = f"expected tool {name!r} was not called (got {called or 'none'})"
            break
    if ok and not expected and called:
        ok = False
        reason = f"unexpected tool calls: {called}"
    if ok:
        for needle in case.expect_contains:
            if needle not in reply:
                ok = False
                reason = f"reply missing substring {needle!r}"
                break

    return Result(case=case, called=called, reply=reply, ok=ok, reason=reason)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--only", type=str, default="", help="Substring filter over case names."
    )
    args = parser.parse_args(argv)

    cases = _load(args.file)
    if args.only:
        cases = [c for c in cases if args.only in c.name]
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    passes = 0
    fails: list[Result] = []
    for case in cases:
        result = _run_case(case)
        marker = "PASS" if result.ok else "FAIL"
        print(f"[{marker}] {case.name}: tools={result.called} reply={result.reply!r}")
        if result.ok:
            passes += 1
        else:
            print(f"       -> {result.reason}")
            fails.append(result)

    print(f"\n{passes}/{len(cases)} passed")
    return 0 if not fails else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
