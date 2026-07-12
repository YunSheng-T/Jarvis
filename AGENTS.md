# Jarvis — Agent Context

This file is the persistent memory for any coding agent (Codex, Claude, etc.) working in this repo.
Read it fully before making changes.

## 1. Vision

Build a "Jarvis"-style personal assistant inspired by Iron Man — a voice-first, always-on
assistant that goes deeper than Siri: hotword wake, low-latency conversation, tool use,
and system-level control.

**Target end-state**: a wake-word triggered assistant that can hear, think, speak,
and execute actions on the host machine (open apps, control media, query calendar,
run shell, drive MCP tools, eventually control smart home).

## 2. Deployment target

- **Primary host (production)**: an idle Huawei MateBook (2022) running **Ubuntu**
  (likely 22.04 or 24.04, may upgrade), with an entry-level NVIDIA discrete GPU.
  Long-term this box may migrate to Fedora 40 KDE or Arch. Everything must stay
  distro-agnostic where feasible.
- **Development host**: macOS (Apple Silicon). Code is authored on Mac, pushed to
  GitHub, pulled and run on the Ubuntu box.
- **Later**: may split into "brain server" + Raspberry Pi voice terminal.

**Design rule**: All platform-specific code lives behind `src/jarvis/platform_adapter/`.
Never call `osascript` / `dbus` / `wtype` directly from business logic.

## 3. Tech decisions (locked-in for Phase 1)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.11+ | Fast iteration; native libs for audio + ML |
| Package mgmt | `uv` | Fast, reproducible, lockfile-based |
| Wake word | `openWakeWord` (fallback: Porcupine) | Free, local, custom "Jarvis" trainable |
| ASR | `faster-whisper` (small on CPU, medium on GPU) | Local, fast, CUDA on Ubuntu |
| LLM | OpenAI `gpt-4o` / `gpt-4.1` first; Ollama (Qwen2.5 / Llama 3.x) fallback | Cloud for quality, local for privacy/offline |
| TTS | `Piper` (local, British butler voice) + optional ElevenLabs streaming | Piper is free + fast; EL for premium voice |
| Audio I/O | `sounddevice` on top of PipeWire (Linux) / CoreAudio (Mac) | Cross-platform |
| Orchestration | Simple async pipeline in-process; upgrade to MCP tools later | KISS for Phase 1 |
| Daemon | `systemd --user` service (Linux); `launchd` plist (Mac) | Standard, per-user, auto-restart |
| Config | `pydantic-settings` + `.env` + `configs/*.toml` | Type-safe, layered |

Do **not** silently swap these without noting a rationale in this file.

## 4. Repository layout

```
Jarvis/
├── AGENTS.md                 # you are here
├── README.md
├── pyproject.toml            # uv-managed
├── .env.example
├── configs/
│   └── default.toml          # non-secret defaults
├── src/jarvis/
│   ├── __init__.py
│   ├── __main__.py           # `python -m jarvis`
│   ├── app.py                # main pipeline wiring
│   ├── settings.py           # pydantic-settings
│   ├── logging_setup.py
│   ├── pipeline/
│   │   ├── wake.py           # wake-word detection
│   │   ├── asr.py            # speech-to-text
│   │   ├── brain.py          # LLM + tool routing
│   │   ├── tts.py            # text-to-speech
│   │   └── audio_io.py       # mic/speaker abstraction
│   ├── platform_adapter/
│   │   ├── base.py           # abstract adapter interface
│   │   ├── macos.py          # AppleScript / osascript
│   │   └── linux.py          # dbus / playerctl / wtype
│   └── tools/
│       ├── registry.py       # tool registration
│       └── system.py         # open app, volume, notify, etc.
├── scripts/
│   ├── install-linux.sh      # apt + uv sync + model download
│   ├── install-macos.sh
│   └── dev.sh                # run locally
├── systemd/
│   └── jarvis.service        # user unit
└── docs/
    ├── roadmap.md
    ├── linux-setup.md        # Ubuntu-specific bootstrap
    └── migration.md          # move machines / distros
```

## 5. Phase roadmap

- **Phase 0 (now)**: skeleton + config + logging + platform adapter stubs + docs. No audio yet.
- **Phase 1**: text-only REPL → LLM → tool call → response. Prove the brain + tools loop.
- **Phase 2**: add ASR (mic → text) and TTS (text → speaker). Push-to-talk key.
- **Phase 3**: add wake word. Always-on daemon via systemd. Barge-in support.
- **Phase 4**: MCP tools (browser, files, calendar). HUD overlay. Home Assistant.
- **Phase 5**: local-only mode (Ollama + whisper + Piper) validated end-to-end.

Each phase must remain runnable end-to-end. Do not merge half-integrated features.

## 6. Working agreements for coding agents

- **Cross-platform first**: any Linux-only or Mac-only call goes through `platform_adapter`.
- **No secrets in code**: read from env / `.env`. `.env.example` documents required keys.
- **Ask before adding heavy deps** (>50MB installed, or native build required). Prefer pure-Python.
- **Never `git commit` or `git push`** unless the user explicitly asks.
- **Logs > prints**: use the `logging` module wired in `logging_setup.py`.
- **Small PRs**: one phase or one concern at a time.
- **Update this file** when a locked-in decision changes.

## 7. Prior conversation highlights (summary)

- User wants a Siri replacement / Jarvis-style butler assistant.
- Explored Mac feasibility: doable but Siri cannot truly be replaced due to
  system sandboxing; deep automation on macOS hits TCC and permissions walls.
- Decided Linux is the better long-term host for depth of control + hardware
  integration + local model performance.
- User has an idle Huawei MateBook (2022) already running Ubuntu (dual-boot with
  Windows) with a discrete GPU. That machine becomes the Jarvis host.
- No USB stick for reimaging right now → staying on Ubuntu for now, may migrate
  to Fedora 40 KDE or Arch later. Migration path must stay clean.
- Development happens on macOS; code lives in this repo; Ubuntu pulls via git.
- GitHub remote: https://github.com/YunSheng-T/Jarvis.git
