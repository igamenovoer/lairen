"""CLI update flow: rebind a saved account to a new provider home."""

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


def test_update_same_identity_refreshes_blob(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    new_home = tmp_path / "new-home"
    write_codex_home(old_home, "alice@example.com", "old-refresh")
    write_codex_home(new_home, "alice@example.com", "new-refresh")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["register", "codex", "--home", str(old_home), "--alias", "work"]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["update", "work", "--home", str(new_home)])
    assert result.exit_code == 0, result.output
    assert "updated codex/alice@example.com" in result.output
    assert "alias=work" in result.output

    result = runner.invoke(cli, ["show", "work"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["usage"]["last_refresh"] == "new-refresh"
    assert payload["account"]["source_home"] == str(new_home)
    assert payload["account"]["alias"] == "work"

    result = runner.invoke(cli, ["list", "--json"])
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
    assert (
        runner.invoke(
            cli, ["register", "codex", "--home", str(old_home), "--alias", "work"]
        ).exit_code
        == 0
    )

    result = runner.invoke(cli, ["update", "work", "--home", str(new_home)])
    assert result.exit_code == 0, result.output
    assert "updated codex/old@example.com -> codex/new@example.com" in result.output

    result = runner.invoke(cli, ["list", "--json"])
    accounts = json.loads(result.output)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "new@example.com"
    assert accounts[0]["alias"] == "work"
    assert accounts[0]["label"] == "new@example.com"
    assert accounts[0]["source_home"] == str(new_home)

    keys = set(read_store(tmp_path))
    assert keys == {"codex:new@example.com"}

    result = runner.invoke(cli, ["show", "work"])
    assert result.exit_code == 0, result.output


def test_update_preserves_a_custom_label(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    new_home = tmp_path / "new-home"
    write_codex_home(old_home, "old@example.com", "old-refresh")
    write_codex_home(new_home, "new@example.com", "new-refresh")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli,
            [
                "register",
                "codex",
                "--home",
                str(old_home),
                "--label",
                "custom-label",
                "--alias",
                "work",
            ],
        ).exit_code
        == 0
    )

    assert runner.invoke(cli, ["update", "work", "--home", str(new_home)]).exit_code == 0

    result = runner.invoke(cli, ["list", "--json"])
    assert json.loads(result.output)[0]["label"] == "custom-label"


def test_update_refuses_to_merge_existing_accounts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    alice_home = tmp_path / "alice"
    bob_home = tmp_path / "bob"
    write_codex_home(alice_home, "alice@example.com", "alice-refresh")
    write_codex_home(bob_home, "bob@example.com", "bob-refresh")
    runner = CliRunner()
    assert runner.invoke(cli, ["register", "codex", "--home", str(alice_home)]).exit_code == 0
    assert runner.invoke(cli, ["register", "codex", "--home", str(bob_home)]).exit_code == 0

    result = runner.invoke(cli, ["update", "codex/alice@example.com", "--home", str(bob_home)])
    assert result.exit_code == 1
    assert "belongs to existing account codex/bob@example.com" in result.output

    result = runner.invoke(cli, ["list", "--json"])
    assert len(json.loads(result.output)) == 2


def test_update_requires_a_readable_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    old_home = tmp_path / "old-home"
    empty_home = tmp_path / "empty-home"
    write_codex_home(old_home, "alice@example.com", "old-refresh")
    empty_home.mkdir()
    runner = CliRunner()
    assert runner.invoke(cli, ["register", "codex", "--home", str(old_home)]).exit_code == 0

    result = runner.invoke(cli, ["update", "codex/alice@example.com", "--home", str(empty_home)])
    assert result.exit_code == 1
    assert "no codex login" in result.output
