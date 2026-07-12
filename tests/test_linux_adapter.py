from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis.platform_adapter import linux


def test_set_volume_reports_missing_pactl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(linux.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="required command is not installed: pactl"):
        linux.LinuxAdapter().set_volume(80)


def test_run_reports_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(linux.shutil, "which", lambda _: "/usr/bin/pactl")
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(RuntimeError, match=r"command failed \(1\): pactl"):
        linux.LinuxAdapter().set_volume(80)


def test_install_app_uses_snap_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(linux.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls: list[list[str]] = []

    def fake_run(cmd, check=False):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(linux.subprocess, "run", fake_run)

    result = linux.LinuxAdapter().install_app("Spotify")

    assert "snap" in result
    assert calls and calls[0] == ["sudo", "snap", "install", "spotify"]


def test_install_app_falls_back_to_apt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        linux.shutil,
        "which",
        lambda name: None if name == "snap" else f"/usr/bin/{name}",
    )
    calls: list[list[str]] = []

    def fake_run(cmd, check=False):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(linux.subprocess, "run", fake_run)

    result = linux.LinuxAdapter().install_app("htop")

    assert "apt" in result
    assert ["sudo", "apt-get", "install", "-y", "htop"] in calls


def test_open_app_falls_back_when_gtk_launch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        linux.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"gtk-launch", "spotify"} else None,
    )

    calls: list[list[str]] = []

    class FakeProc:
        def __init__(self, cmd):  # type: ignore[no-untyped-def]
            self.cmd = cmd
            self.returncode = 0 if cmd[0] == "spotify" else 1

        def communicate(self, timeout=None):  # type: ignore[no-untyped-def]
            if self.cmd[0] == "spotify":
                raise linux.subprocess.TimeoutExpired(self.cmd, timeout)
            return b"", b"gtk-launch: no such application spotify\n"

    def fake_popen(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return FakeProc(cmd)

    monkeypatch.setattr(linux.subprocess, "Popen", fake_popen)

    linux.LinuxAdapter().open_app("spotify")

    assert calls[0] == ["gtk-launch", "spotify"]
    assert ["spotify"] in calls


def test_play_music_uses_spotify_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        linux.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "spotify" else None,
    )

    captured: list[list[str]] = []

    class FakeProc:
        returncode = 0

        def communicate(self, timeout=None):  # type: ignore[no-untyped-def]
            raise linux.subprocess.TimeoutExpired("spotify", timeout)

    def fake_popen(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        captured.append(cmd)
        return FakeProc()

    monkeypatch.setattr(linux.subprocess, "Popen", fake_popen)

    result = linux.LinuxAdapter().play_music("Taylor Swift")

    assert captured == [["spotify", "--uri", "spotify:search:Taylor+Swift"]]
    assert "Taylor Swift" in result
