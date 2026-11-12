"""CLI update flow: rebind an account to a new provider home."""

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


def write_codex_home(path: Path, email: str, last_refresh: str) -> None:
    path.mkdir(parents=True)
    (path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email, "name": "Test"}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                    "account_id": "acct-1",
                },
                "last_refresh": last_refresh,
            }
        ),
        encoding="utf-8",
    )


def read_store(tmp_path: Path) -> dict[str, str]:
    path = tmp_path / "lairen" / "data" / "credentials.json"
    return json.loads(path.read_text(encoding="utf-8"))


def add(runner: CliRunner, home: Path, *extra: str) -> None:
    result = runner.invoke(
        cli,
        ["account", "add", "--provider", "codex", "--home", str(home), *extra],
    )
    assert result.exit_code == 0, result.output


def test_update_same_identity_refreshes_auth_and_holder(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    new_home = tmp_path / "new-home"
    write_codex_home(old_home, "alice@example.com", "old-refresh")
    write_codex_home(new_home, "alice@example.com", "new-refresh")
    runner = CliRunner()
    add(runner, old_home, "--alias", "work")

    result = runner.invoke(cli, ["account", "update", "work", "--home", str(new_home)])
    assert result.exit_code == 0, result.output
    assert "updated codex/alice@example.com" in result.output
    assert "alias: work" in result.output

    result = runner.invoke(cli, ["account", "show", "work", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["auth"]["usage"]["last_refresh"] == "new-refresh"
    assert payload["auth"]["source_home"] == str(new_home)
    assert payload["holder"]["home"] == str(new_home)
    assert payload["alias"] == "work"

    result = runner.invoke(cli, ["account", "list", "--json"])
    accounts = json.loads(result.output)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "alice@example.com"


def test_update_rebinds_changed_identity_and_keeps_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    new_home = tmp_path / "new-home"
    write_codex_home(old_home, "old@example.com", "old-refresh")
    write_codex_home(new_home, "new@example.com", "new-refresh")
    runner = CliRunner()
    add(runner, old_home, "--alias", "work")

    result = runner.invoke(cli, ["account", "update", "work", "--home", str(new_home)])
    assert result.exit_code == 0, result.output
    assert "updated codex/old@example.com -> codex/new@example.com" in result.output

    result = runner.invoke(cli, ["account", "list", "--json"])
    accounts = json.loads(result.output)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "new@example.com"
    assert accounts[0]["alias"] == "work"
    assert accounts[0]["label"] == "new@example.com"
    assert accounts[0]["auth"]["source_home"] == str(new_home)
    assert accounts[0]["holder"]["home"] == str(new_home)

    keys = set(read_store(tmp_path))
    assert keys == {"codex:new@example.com"}

    result = runner.invoke(cli, ["account", "show", "work", "--json"])
    assert result.exit_code == 0, result.output


def test_update_preserves_a_custom_label(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    new_home = tmp_path / "new-home"
    write_codex_home(old_home, "old@example.com", "old-refresh")
    write_codex_home(new_home, "new@example.com", "new-refresh")
    runner = CliRunner()
    add(runner, old_home, "--label", "custom-label", "--alias", "work")

    assert runner.invoke(
        cli, ["account", "update", "work", "--home", str(new_home)]
    ).exit_code == 0

    result = runner.invoke(cli, ["account", "list", "--json"])
    assert json.loads(result.output)[0]["label"] == "custom-label"


def test_update_refuses_to_merge_existing_accounts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    alice_home = tmp_path / "alice"
    bob_home = tmp_path / "bob"
    write_codex_home(alice_home, "alice@example.com", "alice-refresh")
    write_codex_home(bob_home, "bob@example.com", "bob-refresh")
    runner = CliRunner()
    add(runner, alice_home)
    add(runner, bob_home)

    result = runner.invoke(
        cli,
        ["account", "update", "codex/alice@example.com", "--home", str(bob_home)],
    )
    assert result.exit_code == 1
    assert "belongs to existing account codex/bob@example.com" in result.output

    result = runner.invoke(cli, ["account", "list", "--json"])
    assert len(json.loads(result.output)) == 2


def test_update_requires_a_readable_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    empty_home = tmp_path / "empty-home"
    write_codex_home(old_home, "alice@example.com", "old-refresh")
    empty_home.mkdir()
    runner = CliRunner()
    add(runner, old_home)

    result = runner.invoke(
        cli,
        ["account", "update", "codex/alice@example.com", "--home", str(empty_home)],
    )
    assert result.exit_code == 1
    assert "no codex login" in result.output
