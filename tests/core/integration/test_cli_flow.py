"""End-to-end Click flow with Codex and Kimi fixtures."""

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


def write_codex_home(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": "alice@example.com", "name": "Alice"}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                    "account_id": "acct-1",
                }
            }
        ),
        encoding="utf-8",
    )


def write_kimi_home(path: Path) -> None:
    (path / "credentials").mkdir(parents=True)
    claims = {"user_id": "user-1", "device_id": "device-1"}
    (path / "credentials" / "kimi-code.json").write_text(
        json.dumps(
            {
                "access_token": jwt(claims),
                "refresh_token": jwt({**claims, "exp": 2_000_000_100}),
                "expires_at": 2_000_000_000,
                "scope": "kimi-code",
            }
        ),
        encoding="utf-8",
    )


def test_register_deploy_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    codex_home = tmp_path / "codex-home"
    kimi_home = tmp_path / "kimi-home"
    write_codex_home(codex_home)
    write_kimi_home(kimi_home)

    runner = CliRunner()
    result = runner.invoke(cli, ["register", "codex", "--home", str(codex_home)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["register", "kimi", "--home", str(kimi_home)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["list", "--json"])
    assert result.exit_code == 0, result.output
    accounts = json.loads(result.output)
    refs = {account["ref"] for account in accounts}
    assert refs == {"codex/alice@example.com", "kimi/user-1--device-1"}

    target_codex = tmp_path / "target-codex"
    target_kimi = tmp_path / "target-kimi"
    result = runner.invoke(
        cli,
        ["deploy", "codex/alice@example.com", "--home", str(target_codex)],
    )
    assert result.exit_code == 0, result.output
    assert (target_codex / "auth.json").is_file()

    result = runner.invoke(
        cli,
        ["deploy", "kimi/user-1--device-1", "--home", str(target_kimi)],
    )
    assert result.exit_code == 0, result.output
    assert (target_kimi / "credentials" / "kimi-code.json").is_file()

    result = runner.invoke(cli, ["usage", "--json"])
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    by_ref = {record["ref"]: record for record in records}
    assert by_ref["codex/alice@example.com"]["expires_in_seconds"] > 0
    assert by_ref["kimi/user-1--device-1"]["expires_at"] is not None
