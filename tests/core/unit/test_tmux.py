"""tmux environment application with a fake backend."""

from __future__ import annotations

import pytest

from lairen.errors import LairenError
from lairen.tmux import LibTmuxBackend, apply_tmux_env


class FakeBackend:
    def __init__(
        self,
        *,
        session: dict[str, str] | None = None,
        global_env: dict[str, str] | None = None,
        shell: str | None = "bash",
        foreground: bool = True,
    ) -> None:
        self.envs = {
            "session": dict(session or {}),
            "global": dict(global_env or {}),
        }
        self.shell = shell
        self.foreground = foreground
        self.sent: list[str] = []
        self.set_calls: list[tuple[str, str, str]] = []

    @property
    def pane_id(self) -> str:
        return "%0"

    def scope_label(self, scope: str) -> str:
        if scope == "session":
            return "tmux session $1"
        return "tmux global"

    def getenv(self, scope: str, name: str) -> str | None:
        return self.envs[scope].get(name)

    def setenv(self, scope: str, name: str, value: str) -> None:
        self.set_calls.append((scope, name, value))
        self.envs[scope][name] = value

    def ensure_pane_target(self) -> str:
        if not self.foreground:
            raise LairenError("not the foreground process")
        if self.shell is None:
            raise LairenError("cannot identify the shell")
        return self.shell

    def send_literal(self, command: str) -> None:
        self.sent.append(command)


def test_session_sets_new_value() -> None:
    backend = FakeBackend()

    result = apply_tmux_env(
        backend,
        "KIMI_CODE_HOME",
        "/new",
        inject_pane=False,
        scope="session",
        no_overwrite=False,
    )

    assert result.lines == ["tmux session $1: KIMI_CODE_HOME=/new"]
    assert backend.envs["session"]["KIMI_CODE_HOME"] == "/new"


def test_session_overwrite_reports_old_and_new() -> None:
    backend = FakeBackend(session={"KIMI_CODE_HOME": "/old"})

    result = apply_tmux_env(
        backend,
        "KIMI_CODE_HOME",
        "/new",
        inject_pane=False,
        scope="session",
        no_overwrite=False,
    )

    assert result.lines == [
        "tmux session $1: KIMI_CODE_HOME=/old -> /new"
    ]
    assert backend.envs["session"]["KIMI_CODE_HOME"] == "/new"


def test_same_value_reports_new_only_without_writing() -> None:
    backend = FakeBackend(session={"KIMI_CODE_HOME": "/same"})

    result = apply_tmux_env(
        backend,
        "KIMI_CODE_HOME",
        "/same",
        inject_pane=False,
        scope="session",
        no_overwrite=False,
    )

    assert result.lines == ["tmux session $1: KIMI_CODE_HOME=/same"]
    assert backend.set_calls == []


def test_no_overwrite_conflict_aborts_before_mutation() -> None:
    backend = FakeBackend(session={"KIMI_CODE_HOME": "/old"})

    with pytest.raises(LairenError, match="already sets"):
        apply_tmux_env(
            backend,
            "KIMI_CODE_HOME",
            "/new",
            inject_pane=True,
            scope="session",
            no_overwrite=True,
        )

    assert backend.envs["session"]["KIMI_CODE_HOME"] == "/old"
    assert backend.set_calls == []
    assert backend.sent == []


def test_pane_injection_sends_export() -> None:
    backend = FakeBackend(shell="bash")

    result = apply_tmux_env(
        backend,
        "CODEX_HOME",
        "/new",
        inject_pane=True,
        scope=None,
        no_overwrite=False,
    )

    assert result.lines == ["tmux pane %0: CODEX_HOME=/new"]
    assert backend.sent == [result.export_text]
    assert result.export_text.startswith("export CODEX_HOME=")


def test_combined_scope_then_pane() -> None:
    backend = FakeBackend(session={"CODEX_HOME": "/old"}, shell="bash")

    result = apply_tmux_env(
        backend,
        "CODEX_HOME",
        "/new",
        inject_pane=True,
        scope="session",
        no_overwrite=False,
    )

    assert result.lines == [
        "tmux session $1: CODEX_HOME=/old -> /new",
        "tmux pane %0: CODEX_HOME=/new",
    ]
    assert backend.sent == [result.export_text]


def test_pane_requires_foreground_process() -> None:
    backend = FakeBackend(foreground=False)

    with pytest.raises(LairenError, match="foreground"):
        apply_tmux_env(
            backend,
            "CODEX_HOME",
            "/new",
            inject_pane=True,
            scope=None,
            no_overwrite=False,
        )

    assert backend.sent == []


def test_pane_requires_a_shell() -> None:
    backend = FakeBackend(shell=None)

    with pytest.raises(LairenError, match="identify the shell"):
        apply_tmux_env(
            backend,
            "CODEX_HOME",
            "/new",
            inject_pane=True,
            scope=None,
            no_overwrite=False,
        )

    assert backend.sent == []


def test_no_overwrite_requires_a_scope() -> None:
    backend = FakeBackend()

    with pytest.raises(LairenError, match="--no-overwrite requires"):
        apply_tmux_env(
            backend,
            "CODEX_HOME",
            "/new",
            inject_pane=True,
            scope=None,
            no_overwrite=True,
        )


def test_global_scope_uses_global_environment() -> None:
    backend = FakeBackend(global_env={"CODEX_HOME": "/old"})

    result = apply_tmux_env(
        backend,
        "CODEX_HOME",
        "/new",
        inject_pane=False,
        scope="global",
        no_overwrite=False,
    )

    assert result.lines == ["tmux global: CODEX_HOME=/old -> /new"]
    assert backend.envs["global"]["CODEX_HOME"] == "/new"


def test_detected_shell_drives_pane_syntax() -> None:
    backend = FakeBackend(shell="fish")

    result = apply_tmux_env(
        backend,
        "CODEX_HOME",
        "/new",
        inject_pane=True,
        scope=None,
        no_overwrite=False,
    )

    assert result.export_text.startswith("set -gx CODEX_HOME")
    assert backend.sent == [result.export_text]


def test_explicit_shell_overrides_detected_shell() -> None:
    backend = FakeBackend(shell="fish")

    result = apply_tmux_env(
        backend,
        "CODEX_HOME",
        "/new",
        inject_pane=True,
        scope=None,
        no_overwrite=False,
        shell_override="bash",
    )

    assert result.export_text.startswith("export CODEX_HOME=")
    assert backend.sent == [result.export_text]


def test_libtmux_backend_rejects_outside_tmux(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)

    with pytest.raises(LairenError, match="tmux integration requires"):
        LibTmuxBackend.from_env()
