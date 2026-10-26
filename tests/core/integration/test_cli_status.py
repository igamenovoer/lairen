"""CLI project status with real project homes and the deployment ledger."""

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


def write_codex(
    home: Path,
    email: str = "alice@example.com",
    last_refresh: str = "refresh-1",
    expires: int = 2_000_000_000,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email}),
                    "access_token": jwt({"exp": expires}),
                    "account_id": "acct-1",
                },
                "last_refresh": last_refresh,
            }
        ),
        encoding="utf-8",
    )


def write_kimi(
    home: Path,
    user_id: str = "user-1",
    device_id: str = "device-1",
    expires: int = 2_000_000_000,
) -> None:
    credentials = home / "credentials"
    credentials.mkdir(parents=True)
    claims = {"user_id": user_id, "device_id": device_id}
    (credentials / "kimi-code.json").write_text(
        json.dumps(
            {
                "access_token": jwt(claims),
                "refresh_token": jwt({**claims, "exp": expires + 100}),
                "expires_at": expires,
                "scope": "kimi-code",
            }
        ),
        encoding="utf-8",
    )


def test_status_reports_current_registered_account(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    write_codex(project / ".codex")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli,
            [
                "register",
                "codex",
                "--home",
                str(project / ".codex"),
                "--alias",
                "work",
            ],
        ).exit_code
        == 0
    )

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert f"project: {project}" in result.output
    assert "codex/alice@example.com" in result.output
    assert "work" in result.output
    assert "current" in result.output
    assert "\x1b[" not in result.output

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    account = payload["accounts"][0]
    assert account["state"] == "current"
    assert account["alias"] == "work"
    assert account["leases"] == []


def test_status_flags_unregistered_and_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    write_codex(project / ".codex")
    runner = CliRunner()

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert "unregistered" in result.output
    assert f"lairen register codex --home {project / '.codex'}" in result.output

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 1
    assert "strict status failed" in result.output

    result = runner.invoke(cli, ["status", str(project), "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["accounts"][0]["state"] == "unregistered"


def test_status_flags_invalid_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex" / "auth.json").write_text("not json", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert "invalid" in result.output

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 1
    assert "strict status failed" in result.output


def test_status_detects_drifted_credential(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    write_codex(project / ".codex", last_refresh="old")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["register", "codex", "--home", str(project / ".codex")]
        ).exit_code
        == 0
    )
    write_codex(
        project / ".codex",
        last_refresh="new",
        expires=2_000_100_000,
    )

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert "drifted" in result.output
    assert "project expires" in result.output

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 1

    result = runner.invoke(cli, ["status", str(project), "--json"])
    account = json.loads(result.output)["accounts"][0]
    assert account["state"] == "drifted"
    assert account["expires_at"]
    assert account["registry_expires_at"]


def test_status_shows_other_projects_from_the_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    write_codex(project_a / ".codex")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli,
            [
                "register",
                "codex",
                "--home",
                str(project_a / ".codex"),
                "--alias",
                "work",
            ],
        ).exit_code
        == 0
    )
    result = runner.invoke(
        cli, ["deploy", "work", "--home", str(project_b / ".codex")]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["status", str(project_a)])
    assert result.exit_code == 0, result.output
    assert str(project_b) in result.output

    result = runner.invoke(cli, ["status", str(project_a), "--json"])
    account = json.loads(result.output)["accounts"][0]
    leases = account["leases"]
    assert len(leases) == 1
    assert leases[0]["project"] == str(project_b)
    assert leases[0]["home"] == str(project_b / ".codex")
    assert leases[0]["deployed_at"]
    assert leases[0]["legacy"] is False
    assert leases[0]["live"] is True

    log = tmp_path / "lairen" / "state" / "deployments.jsonl"
    log.unlink()
    result = runner.invoke(cli, ["status", str(project_a)])
    assert result.exit_code == 0, result.output
    assert "(last deploy)" in result.output


def test_status_marks_an_overwritten_lease(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    write_codex(project_a / ".codex", email="alice@example.com")
    write_codex(project_b / ".codex", email="bob@example.com")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["register", "codex", "--home", str(project_a / ".codex"),
                  "--alias", "alice"]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["register", "codex", "--home", str(project_b / ".codex"),
                  "--alias", "bob"]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["deploy", "alice", "--home", str(project_b / ".codex")]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["deploy", "bob", "--home", str(project_b / ".codex")]
        ).exit_code
        == 0
    )

    result = runner.invoke(cli, ["status", str(project_a)])
    assert result.exit_code == 0, result.output
    assert "(overwritten)" in result.output

    result = runner.invoke(cli, ["status", str(project_a), "--json"])
    leases = json.loads(result.output)["accounts"][0]["leases"]
    assert len(leases) == 1
    assert leases[0]["live"] is False


def test_status_reports_both_providers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    write_codex(project / ".codex")
    write_kimi(project / ".kimi-code")
    runner = CliRunner()
    assert (
        runner.invoke(
            cli, ["register", "codex", "--home", str(project / ".codex")]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli, ["register", "kimi", "--home", str(project / ".kimi-code")]
        ).exit_code
        == 0
    )

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {account["provider"] for account in payload["accounts"]} == {
        "codex",
        "kimi",
    }
    assert all(account["state"] == "current" for account in payload["accounts"])

    result = runner.invoke(
        cli, ["status", str(project), "--provider", "codex", "--json"]
    )
    payload = json.loads(result.output)
    assert {account["provider"] for account in payload["accounts"]} == {"codex"}


def test_status_with_no_homes_is_success_and_read_only(tmp_path, monkeypatch) -> None:
    state_root = tmp_path / "lairen"
    monkeypatch.setenv("LAIREN_HOME", str(state_root))
    project = tmp_path / "empty-project"
    project.mkdir()
    runner = CliRunner()

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert "no provider homes found" in result.output
    assert not state_root.exists()

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["accounts"] == []
