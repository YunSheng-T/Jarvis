from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.memory import Memory


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "memory.sqlite3"


def test_append_and_load_round_trip(db_path: Path) -> None:
    memory = Memory(db_path)
    try:
        memory.append({"role": "system", "content": "you are jarvis"})
        memory.append({"role": "user", "content": "hi"})
        memory.append({"role": "assistant", "content": "hello"})
    finally:
        memory.close()

    reopened = Memory(db_path)
    try:
        assert [m["role"] for m in reopened.load()] == ["system", "user", "assistant"]
    finally:
        reopened.close()


def test_reset_starts_new_session(db_path: Path) -> None:
    memory = Memory(db_path)
    try:
        memory.append({"role": "user", "content": "first"})
        first_session = memory.session_id
        new_id = memory.reset()
        assert new_id != first_session
        assert memory.load() == []
        memory.append({"role": "user", "content": "second"})
        assert [m["content"] for m in memory.load()] == ["second"]
    finally:
        memory.close()


def test_visible_history_filters_and_limits(db_path: Path) -> None:
    memory = Memory(db_path)
    try:
        memory.append({"role": "system", "content": "sys"})
        memory.append({"role": "user", "content": "u1"})
        memory.append({"role": "assistant", "content": "a1"})
        memory.append({"role": "tool", "content": "tool payload"})
        memory.append({"role": "user", "content": "u2"})
        memory.append({"role": "assistant", "content": "a2"})

        assert [m["content"] for m in memory.visible_history(limit=10)] == [
            "u1",
            "a1",
            "u2",
            "a2",
        ]
        assert [m["content"] for m in memory.visible_history(limit=2)] == ["u2", "a2"]
    finally:
        memory.close()


def test_in_memory_backend_is_isolated() -> None:
    memory = Memory(":memory:")
    try:
        memory.append({"role": "user", "content": "hi"})
        assert [m["content"] for m in memory.load()] == ["hi"]
    finally:
        memory.close()


def test_memory_is_safe_across_threads(db_path: Path) -> None:
    import threading

    memory = Memory(db_path)
    try:
        errors: list[Exception] = []

        def worker(prefix: str) -> None:
            try:
                for i in range(10):
                    memory.append(
                        {"role": "user", "content": f"{prefix}-{i}"}
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(name,)) for name in ("A", "B", "C")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(memory.load()) == 30
    finally:
        memory.close()
