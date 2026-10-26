"""CLI scan flow with Codex and Kimi fixtures."""

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


def write_codex(home: Path, email: str) -> None:
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text(
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


def write_kimi(home: Path, user_id: str, device_id: str) -> None:
    credentials = home / ".kimi-code" / "credentials"
    credentials.mkdir(parents=True)
    (credentials / "kimi-code.json").write_text(
        json.dumps(
            {
                "access_token": jwt({"user_id": user_id, "device_id": device_id}),
                "refresh_token": jwt({"user_id": user_id, "device_id": device_id}),
                "expires_at": 2_000_000_000,
                "scope": "kimi-code",
            }
        ),
        encoding="utf-8",
    )


def test_scan_and_register(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    workspace = tmp_path / "workspace"
    write_codex(workspace / "project-a", "alice@example.com")
    write_kimi(workspace / "project-b", "user-1", "device-1")

    runner = CliRunner()
    result = runner.invoke(cli, ["scan", str(workspace), "--json"])
    assert result.exit_code == 0, result.output
    hits = json.loads(result.output)
    assert {hit["ref"] for hit in hits} == {
        "codex/alice@example.com",
        "kimi/user-1--device-1",
    }

    result = runner.invoke(cli, ["scan", str(workspace), "--register"])
    assert result.exit_code == 0, result.output
    assert "registered codex/alice@example.com" in result.output
    assert "registered kimi/user-1--device-1" in result.output

    result = runner.invoke(cli, ["list", "--json"])
    assert result.exit_code == 0, result.output
    accounts = json.loads(result.output)
    assert {account["ref"] for account in accounts} == {
        "codex/alice@example.com",
        "kimi/user-1--device-1",
    }
