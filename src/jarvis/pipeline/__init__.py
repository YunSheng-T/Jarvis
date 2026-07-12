"""Pipeline stages: audio_io → wake → asr → brain → tts.

Each module is thin and swappable; Phase 0 only wires `brain`.
"""
