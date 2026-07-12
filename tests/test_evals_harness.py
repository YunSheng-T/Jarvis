from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evals import run as evals_run
from jarvis.tools import registry


class _StubBrain:
    """A stand-in for jarvis.pipeline.brain.Brain used inside the eval harness.

    It ignores conversation state and simply calls whichever tools the case
    author wanted, so we can exercise the pass/fail plumbing without hitting
    a real model or performing any side effects.
    """

    def __init__(self, tools_to_call: list[str], reply: str = "ok") -> None:
        self._tools = tools_to_call
        self._reply = reply

    # Match the "Brain(memory=...)" call signature evals.run uses.
    def __call__(self, *_args: Any, **_kwargs: Any) -> _StubBrain:
        return self

    def ask(self, _prompt: str) -> str:
        for name in self._tools:
            tool = registry.get(name)
            if tool is not None:
                tool.func()
        return self._reply


@pytest.fixture()
def suite_file(tmp_path: Path) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {"name": "needs_clock", "prompt": "time?", "expect_tools": ["clock"]},
                {"name": "chatty", "prompt": "hi", "expect_tools": []},
            ]
        )
    )
    return path


def test_harness_reports_pass(
    monkeypatch: pytest.MonkeyPatch,
    suite_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(evals_run, "Brain", _StubBrain(["clock"]))

    exit_code = evals_run.main(["--file", str(suite_file), "--only", "needs_clock"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "[PASS] needs_clock" in output


def test_harness_reports_fail_when_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
    suite_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(evals_run, "Brain", _StubBrain([]))

    exit_code = evals_run.main(["--file", str(suite_file), "--only", "needs_clock"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[FAIL] needs_clock" in output
    assert "expected tool 'clock' was not called" in output
