"""Deploy overwrite protection for refreshed target credentials."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from click.testing import CliRunner

from lairen.cli import cli


def b64(value: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).rstrip(b"=").decode("ascii")


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def write_codex(
    home: Path,
    email: str = "alice@example.com",
    last_refresh: str = "old-refresh",
    expires: int = 2_000_000_000,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email, "name": "Test"}),
                    "access_token": jwt({"exp": expires}),
                    "account_id": "acct-1",
                },
                "last_refresh": last_refresh,
            }
        ),
        encoding="utf-8",
    )


def register(runner: CliRunner, home: Path, alias: str) -> None:
    result = runner.invoke(cli, ["register", "codex", "--home", str(home), "--alias", alias])
    assert result.exit_code == 0, result.output


def read_refresh(path: Path) -> str:
    data = json.loads((path / "auth.json").read_text(encoding="utf-8"))
    return str(data["last_refresh"])


def test_deploy_refuses_to_overwrite_newer_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target)]).exit_code == 0
    write_codex(target, last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target)])
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.output
    assert "newer credential" in result.output
    assert "lairen sync" in result.output
    assert "--force" in result.output
    assert read_refresh(target) == "new-refresh"


def test_deploy_force_overwrites_newer_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target)]).exit_code == 0
    write_codex(target, last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target), "--force"])
    assert result.exit_code == 0, result.output
    assert "warning: overwriting" in result.output
    assert read_refresh(target) == "old-refresh"


def test_deploy_refresh_captures_newer_same_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target)]).exit_code == 0
    write_codex(target, last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target), "--refresh"])
    assert result.exit_code == 0, result.output
    assert "synced codex/alice@example.com" in result.output
    assert read_refresh(target) == "new-refresh"

    result = runner.invoke(cli, ["show", "work"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["usage"]["last_refresh"] == "new-refresh"


def test_deploy_allows_older_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, last_refresh="new-refresh", expires=2_000_100_000)
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target)]).exit_code == 0
    write_codex(target, last_refresh="stale-refresh", expires=1_999_000_000)

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target)])
    assert result.exit_code == 0, result.output
    assert read_refresh(target) == "new-refresh"


def test_deploy_warns_on_unregistered_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, email="alice@example.com")
    write_codex(target, email="bob@example.com", expires=2_000_100_000)
    runner = CliRunner()
    register(runner, source, "work")

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target)])
    assert result.exit_code == 0, result.output
    assert "unregistered credential" in result.output
    assert read_refresh(target) == "old-refresh"


def test_deploy_blocks_newer_target_of_another_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    alice = tmp_path / "alice"
    bob = tmp_path / "bob"
    target = tmp_path / "target"
    write_codex(alice, email="alice@example.com")
    write_codex(bob, email="bob@example.com")
    runner = CliRunner()
    register(runner, alice, "alice")
    register(runner, bob, "bob")
    assert runner.invoke(cli, ["deploy", "bob", "--home", str(target)]).exit_code == 0
    write_codex(target, email="bob@example.com", expires=2_000_100_000)

    result = runner.invoke(cli, ["deploy", "alice", "--home", str(target)])
    assert result.exit_code == 1
    assert "newer credential for codex/bob@example.com" in result.output
    assert "lairen sync codex/bob@example.com" in result.output


def test_deploy_ignores_formatting_only_difference(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target = tmp_path / "target"
    write_codex(source, last_refresh="same-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target)]).exit_code == 0

    result = runner.invoke(cli, ["sync", "work"])
    assert result.exit_code == 0, result.output
    assert "current codex/alice@example.com" in result.output

    result = runner.invoke(cli, ["deploy", "work", "--home", str(target)])
    assert result.exit_code == 0, result.output
    assert read_refresh(target) == "same-refresh"
