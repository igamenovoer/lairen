"""CLI alias lifecycle with a Codex fixture."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from click.testing import CliRunner

from lairen.cli import cli


def b64(value: dict[str, object]) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def write_codex_home(path: Path, email: str) -> None:
    path.mkdir(parents=True)
    (path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                }
            }
        ),
        encoding="utf-8",
    )


def add(
    runner: CliRunner,
    home: Path,
    *extra: str,
) -> None:
    result = runner.invoke(
        cli,
        ["account", "add", "--provider", "codex", "--home", str(home), *extra],
    )
    assert result.exit_code == 0, result.output


def test_account_add_with_alias_list_and_deploy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    home = tmp_path / "codex-home"
    write_codex_home(home, "alice@example.com")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["account", "add", "--provider", "codex", "--home", str(home), "--alias", "work"],
    )
    assert result.exit_code == 0, result.output
    assert "alias=work" in result.output

    result = runner.invoke(cli, ["account", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["alias"] == "work"

    result = runner.invoke(cli, ["account", "list"])
    assert result.exit_code == 0, result.output
    assert "ALIAS" in result.output

    target = tmp_path / "target-codex"
    result = runner.invoke(cli, ["deploy", "copy", "work", "--home", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "auth.json").is_file()


def test_alias_command_lifecycle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    home = tmp_path / "codex-home"
    write_codex_home(home, "alice@example.com")
    runner = CliRunner()
    add(runner, home)

    result = runner.invoke(
        cli, ["account", "alias", "codex/alice@example.com", "work"]
    )
    assert result.exit_code == 0, result.output
    assert "aliased codex/alice@example.com -> work" in result.output

    result = runner.invoke(cli, ["account", "alias", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"ref": "codex/alice@example.com", "alias": "work"}
    ]

    result = runner.invoke(cli, ["account", "alias", "work"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "work"

    result = runner.invoke(cli, ["account", "alias", "work", "--clear"])
    assert result.exit_code == 0, result.output
    assert "cleared alias" in result.output

    result = runner.invoke(cli, ["account", "alias", "work"])
    assert result.exit_code == 1
    assert "unknown account" in result.output


def test_readd_and_scan_preserve_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    home = tmp_path / "project-a"
    write_codex_home(home / ".codex", "alice@example.com")
    runner = CliRunner()
    add(runner, home / ".codex", "--alias", "work")

    add(runner, home / ".codex")

    result = runner.invoke(
        cli, ["account", "scan", str(home), "--provider", "codex", "--add"]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["account", "list", "--json"])
    accounts = json.loads(result.output)
    assert [account["alias"] for account in accounts] == ["work"]


def test_alias_conflicts_and_invalid_names(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    alice_home = tmp_path / "alice"
    bob_home = tmp_path / "bob"
    write_codex_home(alice_home, "alice@example.com")
    write_codex_home(bob_home, "bob@example.com")
    runner = CliRunner()
    add(runner, alice_home, "--alias", "work")

    result = runner.invoke(
        cli,
        ["account", "add", "--provider", "codex", "--home", str(bob_home), "--alias", "work"],
    )
    assert result.exit_code == 1
    assert "already used" in result.output

    result = runner.invoke(
        cli, ["account", "alias", "codex/alice@example.com", "bad alias"]
    )
    assert result.exit_code == 1
    assert "must start" in result.output
