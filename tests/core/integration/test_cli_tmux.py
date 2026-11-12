"""CLI tmux integration for deploy env."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from click.testing import CliRunner

import lairen.cli as cli_module
from lairen.cli import cli
from lairen.errors import LairenError


def b64(value: dict[str, object]) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def write_codex(home: Path, email: str = "alice@example.com") -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email, "name": "Test"}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                    "account_id": "acct-1",
                },
                "last_refresh": "refresh-1",
            }
        ),
        encoding="utf-8",
    )


def add_account(runner: CliRunner, holder: Path, alias: str = "aj") -> None:
    result = runner.invoke(
        cli,
        [
            "account",
            "add",
            "--provider",
            "codex",
            "--home",
            str(holder),
            "--alias",
            alias,
        ],
    )
    assert result.exit_code == 0, result.output


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


def patch_backend(monkeypatch, backend: FakeBackend) -> None:
    def fake_from_env(cls):
        return backend

    monkeypatch.setattr(
        cli_module.LibTmuxBackend,
        "from_env",
        classmethod(fake_from_env),
    )


def test_deploy_env_tmux_injects_current_pane(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(shell="bash")
    patch_backend(monkeypatch, backend)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines[0].startswith("export CODEX_HOME=")
    assert f"tmux pane %0: CODEX_HOME={holder.resolve()}" in result.output
    assert backend.sent == [lines[0]]


def test_deploy_env_tmux_session_overwrites_and_reports_both_values(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(session={"CODEX_HOME": "/old"})
    patch_backend(monkeypatch, backend)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux-session"])
    assert result.exit_code == 0, result.output
    assert (
        f"tmux session $1: CODEX_HOME=/old -> {holder.resolve()}"
        in result.output
    )
    assert backend.envs["session"]["CODEX_HOME"] == str(holder.resolve())
    assert backend.sent == []


def test_deploy_env_tmux_session_no_overwrite_rejects_conflict(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(session={"CODEX_HOME": "/old"})
    patch_backend(monkeypatch, backend)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--tmux-session", "--no-overwrite"],
    )
    assert result.exit_code == 1
    assert "already sets CODEX_HOME to /old" in result.output
    assert "remove --no-overwrite" in result.output
    assert backend.envs["session"]["CODEX_HOME"] == "/old"
    assert backend.set_calls == []
    assert backend.sent == []


def test_deploy_env_tmux_session_and_pane(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(session={"CODEX_HOME": "/old"}, shell="bash")
    patch_backend(monkeypatch, backend)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--tmux", "--tmux-session"],
    )
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines[0].startswith("export CODEX_HOME=")
    session_line = next(
        index for index, line in enumerate(lines)
        if line.startswith("tmux session $1:")
    )
    pane_line = next(
        index for index, line in enumerate(lines)
        if line.startswith("tmux pane %0:")
    )
    assert session_line < pane_line
    assert backend.sent == [lines[0]]
    assert backend.envs["session"]["CODEX_HOME"] == str(holder.resolve())


def test_deploy_env_tmux_no_print_keeps_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(shell="bash")
    patch_backend(monkeypatch, backend)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--tmux", "--no-print"],
    )
    assert result.exit_code == 0, result.output
    assert "export CODEX_HOME=" not in result.output
    assert f"tmux pane %0: CODEX_HOME={holder.resolve()}" in result.output
    assert backend.sent


def test_deploy_env_rejects_session_and_global_together(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--tmux-session", "--tmux-global"],
    )
    assert result.exit_code == 1
    assert "choose --tmux-session or --tmux-global" in result.output


def test_deploy_env_no_overwrite_requires_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--no-overwrite"],
    )
    assert result.exit_code == 1
    assert "--no-overwrite requires --tmux-session or --tmux-global" in result.output


def test_deploy_env_no_print_requires_tmux(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--no-print"])
    assert result.exit_code == 1
    assert "--no-print requires" in result.output


def test_deploy_env_tmux_requires_foreground(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(foreground=False)
    patch_backend(monkeypatch, backend)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux"])
    assert result.exit_code == 1
    assert "foreground" in result.output
    assert backend.sent == []


def test_deploy_env_tmux_requires_shell(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(shell=None)
    patch_backend(monkeypatch, backend)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux"])
    assert result.exit_code == 1
    assert "identify the shell" in result.output
    assert backend.sent == []


def test_deploy_env_tmux_uses_detected_fish_shell(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(shell="fish")
    patch_backend(monkeypatch, backend)

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux"])
    assert result.exit_code == 0, result.output
    assert "set -gx CODEX_HOME" in result.output
    assert backend.sent[0].startswith("set -gx CODEX_HOME")


def test_deploy_env_tmux_shell_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)
    backend = FakeBackend(shell="fish")
    patch_backend(monkeypatch, backend)

    result = runner.invoke(
        cli,
        ["deploy", "env", "aj", "--tmux", "--shell", "bash"],
    )
    assert result.exit_code == 0, result.output
    assert "export CODEX_HOME=" in result.output
    assert backend.sent[0].startswith("export CODEX_HOME=")


def test_deploy_env_tmux_outside_tmux(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add_account(runner, holder)

    def fake_from_env(cls):
        raise LairenError(
            "tmux integration requires a tmux session; TMUX/TMUX_PANE are not set"
        )

    monkeypatch.setattr(
        cli_module.LibTmuxBackend,
        "from_env",
        classmethod(fake_from_env),
    )

    result = runner.invoke(cli, ["deploy", "env", "aj", "--tmux-session"])
    assert result.exit_code == 1
    assert "tmux integration requires a tmux session" in result.output
