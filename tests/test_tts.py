from __future__ import annotations

from typing import Any

import pytest

from jarvis.pipeline import tts as tts_module


def test_detect_language_english() -> None:
    assert tts_module.detect_language("Hello Jarvis, please play music") == "en"


def test_detect_language_chinese() -> None:
    assert tts_module.detect_language("你好，请随机播放一首歌") == "zh"


def test_detect_language_mixed_prefers_chinese() -> None:
    assert tts_module.detect_language("好的，Spotify 已经打开") == "zh"


def test_stream_sentences_buffers_partial_chunks() -> None:
    chunks = ["Hello ", "world. How ", "are you today?"]
    result = list(tts_module.stream_sentences(chunks))
    assert result == ["Hello world.", "How are you today?"]


def test_stream_sentences_emits_trailing_fragment() -> None:
    result = list(tts_module.stream_sentences(["no terminator here"]))
    assert result == ["no terminator here"]


def test_stream_sentences_handles_chinese_punctuation() -> None:
    result = list(tts_module.stream_sentences(["现在几点？", "香港时间。"]))
    assert result == ["现在几点？", "香港时间。"]


class _FakeEngine:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, text: str, language: str) -> list[tts_module.Utterance]:
        self.calls.append((text, language))
        if self.fail:
            raise tts_module.TTSError("piper missing")
        return [
            tts_module.Utterance(
                pcm=b"\x00\x00" * 32,
                sample_rate=22050,
                channels=1,
                sample_width=2,
                text=text,
            )
        ]


class _FakeAdapter:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak_fallback(self, text: str) -> None:
        self.spoken.append(text)


def test_speaker_say_falls_back_when_piper_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    played: list[Any] = []
    monkeypatch.setattr(tts_module, "_play_pcm", lambda u: played.append(u))

    adapter = _FakeAdapter()
    speaker = tts_module.Speaker(engine=_FakeEngine(fail=True))
    speaker._adapter = adapter

    speaker.say("hello there")

    assert played == []
    assert adapter.spoken == ["hello there"]


def test_speaker_stream_routes_by_language(monkeypatch: pytest.MonkeyPatch) -> None:
    played: list[str] = []
    monkeypatch.setattr(
        tts_module,
        "_play_pcm",
        lambda utterance: played.append(utterance.text),
    )

    engine = _FakeEngine()
    speaker = tts_module.Speaker(engine=engine)

    speaker.stream(["Hello world. ", "你好，Jarvis。"])

    assert [lang for _, lang in engine.calls] == ["en", "zh"]
    assert played == ["Hello world.", "你好，Jarvis。"]
