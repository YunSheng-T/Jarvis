from __future__ import annotations

import pytest

from jarvis import app as app_module
from jarvis.settings import settings


@pytest.fixture(autouse=True)
def _reset_bias_lists() -> None:
    settings.asr.hint_terms = []
    settings.asr.hotwords = []


def test_hint_add_remove_show(capsys: pytest.CaptureFixture[str]) -> None:
    app_module._run_word_list_command("hint", "hint_terms", ["add", "Jarvis", "Spotify"])
    assert settings.asr.hint_terms == ["Jarvis", "Spotify"]

    app_module._run_word_list_command("hint", "hint_terms", ["add", "Spotify", "Taylor"])
    assert settings.asr.hint_terms == ["Jarvis", "Spotify", "Taylor"]

    app_module._run_word_list_command("hint", "hint_terms", ["show"])
    output = capsys.readouterr().out
    assert "Jarvis" in output and "Taylor" in output

    app_module._run_word_list_command("hint", "hint_terms", ["remove", "Spotify"])
    assert settings.asr.hint_terms == ["Jarvis", "Taylor"]

    app_module._run_word_list_command("hint", "hint_terms", ["clear"])
    assert settings.asr.hint_terms == []


def test_hotword_show_when_empty(capsys: pytest.CaptureFixture[str]) -> None:
    app_module._run_word_list_command("hotword", "hotwords", ["show"])
    assert "no hotword" in capsys.readouterr().out


def test_word_list_command_reports_usage_on_missing_words(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app_module._run_word_list_command("hint", "hint_terms", ["add"])
    assert "usage" in capsys.readouterr().out
    assert settings.asr.hint_terms == []
