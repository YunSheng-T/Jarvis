# Roadmap

Living document. Update as phases land. Canonical source of order-of-work.

## Phase 0 — Skeleton *(this commit)*
- [x] Repo layout, `AGENTS.md`, README, licence-free.
- [x] `pyproject.toml` with `uv`.
- [x] `settings.py` (TOML + env), `logging_setup.py`.
- [x] Platform adapter interface + macOS + Linux impls.
- [x] Tool registry with `notify`, `open_app`, `set_volume`.
- [x] Brain stub (works without API key) + tool calling when key present.
- [x] Text REPL entry (`python -m jarvis`).
- [x] Install scripts for Ubuntu + macOS.
- [x] `systemd --user` unit template.

## Phase 1 — Real brain + more tools
- [x] Streaming responses to console.
- [x] Add clock / weather / timer tools; calendar and safe shell-exec deferred.
- [x] Persistent conversation history (SQLite); rolling summary deferred.
- [x] Basic eval harness: script that replays canned prompts and checks tool calls.

## Phase 2 — Voice I/O (push-to-talk)
- [ ] `pipeline/audio_io.py`: mic capture + VAD (webrtcvad).
- [ ] `pipeline/asr.py`: faster-whisper (CPU default, CUDA when available on Ubuntu).
- [ ] `pipeline/tts.py`: Piper local voice; fallback to adapter's `speak_fallback`.
- [ ] Hotkey trigger (Ctrl+`) on Mac and Linux (evdev / pynput).
- [ ] End-to-end: press key → speak → transcribed → LLM reply → spoken back.

## Phase 3 — Wake word + daemon
- [ ] `pipeline/wake.py`: openWakeWord with "jarvis" model.
- [ ] Always-on loop; barge-in (interrupt current TTS on new wake).
- [ ] `systemd --user` autostart on Ubuntu, verified.
- [ ] Menu-bar / tray indicator (`pystray` on Linux; rumps on Mac).

## Phase 4 — Depth
- [ ] MCP client: browser, filesystem, calendar, mail.
- [ ] HUD overlay (Electron/Tauri or GTK layer-shell) with subtitles + waveform.
- [ ] Home Assistant integration (MQTT / REST).
- [ ] Screen context (OCR + vision model) — opt-in.

## Phase 5 — Fully local mode
- [ ] Ollama backend behind `JARVIS_LLM_BASE_URL`.
- [ ] Verified offline flight: no internet, everything still works.
- [ ] Benchmarks: latency budget documented (wake<200ms, ASR<400ms, first token<600ms).
