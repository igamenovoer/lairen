"""CLI sync flow: pull refreshed credentials back into the store."""

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


def write_kimi(
    home: Path,
    user_id: str = "user-1",
    device_id: str = "device-1",
    access_expires: int = 2_000_000_000,
    refresh_expires: int = 2_000_000_100,
    marker: str = "old",
) -> None:
    credentials = home / "credentials"
    credentials.mkdir(parents=True, exist_ok=True)
    claims = {"user_id": user_id, "device_id": device_id, "marker": marker}
    (credentials / "kimi-code.json").write_text(
        json.dumps(
            {
                "access_token": jwt({**claims, "exp": access_expires}),
                "refresh_token": jwt({**claims, "exp": refresh_expires}),
                "expires_at": access_expires,
                "scope": "kimi-code",
            }
        ),
        encoding="utf-8",
    )


def show_usage(tmp_path: Path, ref: str) -> dict[str, object]:
    runner = CliRunner()
    result = runner.invoke(cli, ["show", ref])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["usage"]


def register(runner: CliRunner, home: Path, alias: str) -> None:
    result = runner.invoke(cli, ["register", "codex", "--home", str(home), "--alias", alias])
    assert result.exit_code == 0, result.output


def test_sync_updates_store_from_refreshed_deployment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(project / ".codex")]).exit_code == 0
    write_codex(project / ".codex", last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["sync", "work"])
    assert result.exit_code == 0, result.output
    assert "updated codex/alice@example.com" in result.output
    assert str(project / ".codex") in result.output

    usage = show_usage(tmp_path, "work")
    assert usage["last_refresh"] == "new-refresh"
    assert usage["access_token_expires_at"] == 2_000_100_000

    result = runner.invoke(cli, ["status", str(project)])
    assert result.exit_code == 0, result.output
    assert "current" in result.output

    log = tmp_path / "lairen" / "state" / "deployments.jsonl"
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert any(
        entry.get("action") == "sync" and entry.get("ref") == "codex/alice@example.com"
        for entry in entries
    )


def test_sync_dry_run_reports_without_writing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(project / ".codex")]).exit_code == 0
    write_codex(project / ".codex", last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["sync", "work", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "would update" in result.output
    assert show_usage(tmp_path, "work")["last_refresh"] == "old-refresh"

    result = runner.invoke(cli, ["sync", "work", "--dry-run", "--strict"])
    assert result.exit_code == 1
    assert "strict sync failed" in result.output


def test_sync_skips_identity_change_and_strict_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_codex(source, email="alice@example.com", last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(project / ".codex")]).exit_code == 0
    write_codex(
        project / ".codex",
        email="bob@example.com",
        last_refresh="new-refresh",
        expires=2_000_100_000,
    )

    result = runner.invoke(cli, ["sync", "work"])
    assert result.exit_code == 0, result.output
    assert "now belongs to codex/bob@example.com" in result.output
    assert "run lairen update codex/alice@example.com" in result.output
    assert show_usage(tmp_path, "work")["last_refresh"] == "old-refresh"

    result = runner.invoke(cli, ["sync", "work", "--strict"])
    assert result.exit_code == 1
    assert "strict sync failed" in result.output


def test_sync_never_downgrades_the_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_codex(source, last_refresh="new-refresh", expires=2_000_100_000)
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(project / ".codex")]).exit_code == 0
    write_codex(project / ".codex", last_refresh="stale-refresh", expires=1_999_000_000)

    result = runner.invoke(cli, ["sync", "work"])
    assert result.exit_code == 0, result.output
    assert "current codex/alice@example.com" in result.output
    assert show_usage(tmp_path, "work")["last_refresh"] == "new-refresh"


def test_deploy_refresh_captures_target_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    target_b = tmp_path / "target-b"
    target_c = tmp_path / "target-c"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(target_b / ".codex")]).exit_code == 0
    write_codex(target_b / ".codex", last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(
        cli,
        ["deploy", "work", "--home", str(target_c / ".codex"), "--refresh"],
    )
    assert result.exit_code == 0, result.output
    assert "synced codex/alice@example.com" in result.output
    assert show_usage(tmp_path, "work")["last_refresh"] == "new-refresh"

    deployed = json.loads((target_c / ".codex" / "auth.json").read_text(encoding="utf-8"))
    assert deployed["last_refresh"] == "new-refresh"


def test_sync_home_restricts_sources_and_requires_one_ref(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_codex(source, last_refresh="old-refresh")
    runner = CliRunner()
    register(runner, source, "work")
    assert runner.invoke(cli, ["deploy", "work", "--home", str(project / ".codex")]).exit_code == 0
    write_codex(project / ".codex", last_refresh="new-refresh", expires=2_000_100_000)

    result = runner.invoke(cli, ["sync", "work", "--home", str(project / ".codex")])
    assert result.exit_code == 0, result.output
    assert "updated codex/alice@example.com" in result.output

    result = runner.invoke(cli, ["sync", "--home", str(project / ".codex")])
    assert result.exit_code == 1
    assert "--home requires a REF" in result.output

    result = runner.invoke(cli, ["sync", "work", "other", "--home", str(project / ".codex")])
    assert result.exit_code == 1
    assert "--home accepts only one REF" in result.output


def test_sync_prefers_later_refresh_expiry_for_kimi(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    project = tmp_path / "project"
    write_kimi(source, access_expires=2_000_000_000, refresh_expires=2_000_100_000)
    runner = CliRunner()
    result = runner.invoke(cli, ["register", "kimi", "--home", str(source), "--alias", "kimi-1"])
    assert result.exit_code == 0, result.output
    assert (
        runner.invoke(cli, ["deploy", "kimi-1", "--home", str(project / ".kimi-code")]).exit_code
        == 0
    )
    write_kimi(
        project / ".kimi-code",
        access_expires=2_000_050_000,
        refresh_expires=2_001_000_000,
        marker="new",
    )

    result = runner.invoke(cli, ["sync", "kimi-1"])
    assert result.exit_code == 0, result.output
    assert "updated kimi/user-1--device-1" in result.output

    usage = show_usage(tmp_path, "kimi-1")
    assert usage["refresh_token_expires_at"] == 2_001_000_000
    assert usage["access_token_expires_at"] == 2_000_050_000
