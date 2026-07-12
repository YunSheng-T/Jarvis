# Jarvis

A personal voice-first assistant, built to eventually replace Siri-level assistants
on a dedicated Linux host with wake-word, low-latency conversation, and real system control.

> Status: **Phase 0 — skeleton**. See [`AGENTS.md`](./AGENTS.md) for full context and
> [`docs/roadmap.md`](./docs/roadmap.md) for the phase plan.

## Quick start (dev, text-only)

```bash
# 1. Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install deps
uv sync

# 3. Copy env and configure an LLM backend (optional in Phase 0)
cp .env.example .env
$EDITOR .env

# 4. Run
uv run python -m jarvis
```

## LLM backends

The REPL runs in stub mode until an API key is configured. It supports the
OpenAI Python SDK's compatible providers, including Volcano Engine Ark Agent
Plan. To use Agent Plan, set `ARK_API_KEY`, `JARVIS_LLM_BASE_URL`, and
`JARVIS_LLM_MODEL` in `.env` from the exact values displayed in its console's
**OpenAI SDK** API reference. This prevents accidentally using a different Ark
billing route. `OPENAI_API_KEY` remains supported as an alternative.

## Deployment target

- **Host**: Ubuntu (22.04 / 24.04) on a Huawei MateBook 2022 with NVIDIA dGPU.
- **Dev**: macOS Apple Silicon.
- **Portability**: platform-specific code is isolated in `src/jarvis/platform_adapter/`
  so migrating to Fedora / Arch later is a config swap, not a rewrite.

## Layout

See `AGENTS.md` §4 for the canonical layout and design contracts.

## Roadmap

See `docs/roadmap.md`. TL;DR: text REPL → ASR/TTS → wake word → daemon → MCP tools.

## Migration between machines

See `docs/migration.md`. Short version: it's a git clone + `scripts/install-linux.sh`.
