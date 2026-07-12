"""Layered settings: TOML defaults + env vars + .env overrides.

Priority (lowest -> highest):
  configs/default.toml  <  environment variables  <  .env
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "default.toml"


class LLMConfig(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = 0.4
    system_prompt: str = "You are Jarvis, a concise butler assistant."
    base_url: str | None = None


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    input_device: str = ""
    output_device: str = ""


class WakeConfig(BaseModel):
    enabled: bool = False
    keyword: str = "jarvis"
    sensitivity: float = 0.5


class ASRConfig(BaseModel):
    model: str = "small"
    compute: str = "auto"
    language: str = ""


class TTSConfig(BaseModel):
    engine: str = "piper"
    piper_voice: str = "en_GB-alan-medium"


def _load_toml_defaults() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


class Settings(BaseSettings):
    """Top-level settings object. Env vars use `JARVIS_` prefix and `__` nesting."""

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_nested_delimiter="__",
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")

    llm: LLMConfig = LLMConfig()
    audio: AudioConfig = AudioConfig()
    wake: WakeConfig = WakeConfig()
    asr: ASRConfig = ASRConfig()
    tts: TTSConfig = TTSConfig()

    @classmethod
    def load(cls) -> Settings:
        defaults = _load_toml_defaults()
        return cls(**defaults)


settings = Settings.load()
