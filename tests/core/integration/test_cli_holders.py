"""Holder home, link deployment, env activation, and staleness coverage."""

from __future__ import annotations

import base64
import json
import os
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
                    "id_token": jwt({"email": email, "name": "Test"}),
                    "access_token": jwt({"exp": expires}),
                    "account_id": "acct-1",
                },
                "last_refresh": last_refresh,
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


def account_payload(runner: CliRunner, ref: str = "codex/alice@example.com") -> dict:
    result = runner.invoke(cli, ["account", "show", ref, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_deploy_link_creates_reuses_and_unlinks_symlink(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    project = tmp_path / "project"
    project.mkdir()
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")

    result = runner.invoke(cli, ["deploy", "link", "aj", "--project", str(project)])
    assert result.exit_code == 0, result.output
    target = project / ".codex"
    assert target.is_symlink()
    assert Path(os.path.realpath(target)) == holder.resolve()

    result = runner.invoke(cli, ["deploy", "link", "aj", "--project", str(project)])
    assert result.exit_code == 0, result.output
    assert "already linked" in result.output

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    item = payload["accounts"][0]
    assert item["source"] == "link"
    assert item["link"] == str(target)
    assert item["home"] == str(holder.resolve())
    assert item["state"] == "current"
    assert item["holder_state"] == "ok"
    assert payload["ok"] is True

    result = runner.invoke(cli, ["deploy", "unlink", "aj", "--project", str(project)])
    assert result.exit_code == 1
    assert "without --yes" in result.output

    result = runner.invoke(
        cli, ["deploy", "unlink", "aj", "--project", str(project), "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert not target.exists()
    assert not target.is_symlink()


def test_deploy_link_refuses_real_dirs_and_replaces_foreign_symlinks(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")

    real_project = tmp_path / "real-project"
    (real_project / ".codex").mkdir(parents=True)
    result = runner.invoke(
        cli, ["deploy", "link", "aj", "--project", str(real_project)]
    )
    assert result.exit_code == 1
    assert "is not a symlink" in result.output

    other = tmp_path / "other"
    other.mkdir()
    foreign_project = tmp_path / "foreign-project"
    foreign_project.mkdir()
    target = foreign_project / ".codex"
    target.symlink_to(other, target_is_directory=True)

    result = runner.invoke(
        cli, ["deploy", "link", "aj", "--project", str(foreign_project)]
    )
    assert result.exit_code == 1
    assert "pass --force" in result.output

    result = runner.invoke(
        cli,
        ["deploy", "link", "aj", "--project", str(foreign_project), "--force"],
    )
    assert result.exit_code == 0, result.output
    assert Path(os.path.realpath(target)) == holder.resolve()


def test_deploy_env_outputs_shell_commands(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")

    result = runner.invoke(cli, ["deploy", "env", "aj", "--shell", "bash"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().startswith("export CODEX_HOME=")
    assert str(holder.resolve()) in result.output

    result = runner.invoke(cli, ["deploy", "env", "aj", "--shell", "fish"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().startswith("set -gx CODEX_HOME")

    result = runner.invoke(cli, ["deploy", "env", "aj", "--shell", "powershell"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().startswith("$env:CODEX_HOME")

    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    result = runner.invoke(cli, ["deploy", "env", "aj"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().startswith("set -gx CODEX_HOME")


def test_copy_marks_holder_stale_and_sync_clears_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    project = tmp_path / "project"
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")

    result = runner.invoke(
        cli, ["deploy", "copy", "aj", "--home", str(project / ".codex")]
    )
    assert result.exit_code == 0, result.output
    assert "possibly stale" in result.output

    payload = account_payload(runner)
    assert payload["holder_state"] == "possibly-stale"
    assert payload["holder"]["stale"]["reason"].startswith("deploy copy ->")

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 1
    assert "possibly stale" in result.output
    assert "deploy copy" in result.output
    assert "lairen account sync" in result.output

    result = runner.invoke(
        cli, ["account", "sync", "aj", "--home", str(holder)]
    )
    assert result.exit_code == 0, result.output
    assert account_payload(runner)["holder_state"] == "ok"

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 0, result.output


def test_set_home_requires_matching_identity_and_clear_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    replacement = tmp_path / "replacement"
    other = tmp_path / "other"
    write_codex(holder, email="alice@example.com")
    write_codex(replacement, email="alice@example.com", last_refresh="new")
    write_codex(other, email="bob@example.com")
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")

    result = runner.invoke(cli, ["account", "set-home", "aj", "--home", str(other)])
    assert result.exit_code == 1
    assert "holds codex/bob@example.com" in result.output
    assert "lairen account update" in result.output

    result = runner.invoke(
        cli, ["account", "set-home", "aj", "--home", str(replacement), "--sync"]
    )
    assert result.exit_code == 0, result.output
    payload = account_payload(runner)
    assert payload["holder"]["home"] == str(replacement.resolve())
    assert payload["auth"]["source_home"] == str(replacement.resolve())

    result = runner.invoke(cli, ["account", "clear-home", "aj", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["holder"] is None
    assert payload["holder_state"] == "none"
    assert payload["auth"]["present"] is True

    result = runner.invoke(cli, ["deploy", "link", "aj", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "no holder home" in result.output


def test_holder_only_account_links_then_syncs_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    project = tmp_path / "project"
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "temp", "--holder-only")

    payload = account_payload(runner, "temp")
    assert payload["auth"]["stored"] is False
    assert payload["auth"]["present"] is False
    assert payload["holder"]["home"] == str(holder.resolve())

    result = runner.invoke(
        cli, ["deploy", "copy", "temp", "--home", str(project / ".codex")]
    )
    assert result.exit_code == 1
    assert "no stored auth" in result.output

    result = runner.invoke(
        cli, ["deploy", "link", "temp", "--project", str(project)]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["account", "sync", "temp", "--holder-only"])
    assert result.exit_code == 0, result.output
    payload = account_payload(runner, "temp")
    assert payload["auth"]["stored"] is True
    assert payload["auth"]["present"] is True

    result = runner.invoke(
        cli, ["deploy", "copy", "temp", "--home", str(project / ".codex-2")]
    )
    assert result.exit_code == 0, result.output


def test_status_reports_env_binding_and_strict_fails_when_stale(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    project = tmp_path / "project"
    project.mkdir()
    other = tmp_path / "other"
    write_codex(holder)
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")
    monkeypatch.setenv("CODEX_HOME", str(holder))

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["accounts"] == []
    assert payload["shell"][0]["env_var"] == "CODEX_HOME"
    assert payload["shell"][0]["ref"] == "codex/alice@example.com"
    assert payload["shell"][0]["holder_state"] == "ok"
    assert payload["ok"] is True

    result = runner.invoke(cli, ["status", str(project)])
    assert "shell: CODEX_HOME=" in result.output

    result = runner.invoke(
        cli, ["deploy", "copy", "aj", "--home", str(other / ".codex")]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert json.loads(result.output)["shell"][0]["holder_state"] == "possibly-stale"

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 1
    assert "possibly stale" in result.output


def test_link_source_drift_is_informational_for_strict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    holder = tmp_path / "holder"
    project = tmp_path / "project"
    project.mkdir()
    write_codex(holder, last_refresh="old")
    runner = CliRunner()
    add(runner, holder, "--alias", "aj")
    assert runner.invoke(
        cli, ["deploy", "link", "aj", "--project", str(project)]
    ).exit_code == 0

    write_codex(holder, last_refresh="new", expires=2_000_100_000)
    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["accounts"][0]["source"] == "link"
    assert payload["accounts"][0]["state"] == "drifted"
    assert payload["ok"] is True

    result = runner.invoke(cli, ["status", str(project), "--strict"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["account", "sync", "aj", "--holder-only"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["status", str(project), "--json"])
    assert json.loads(result.output)["accounts"][0]["state"] == "current"
