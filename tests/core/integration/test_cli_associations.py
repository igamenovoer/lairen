"""CLI coverage for deployment listing, availability, and project targets."""

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


def write_kimi_home(path: Path, *, user: str = "user-1", device: str = "device-1") -> None:
    credentials = path / "credentials"
    credentials.mkdir(parents=True)
    claims = {"user_id": user, "device_id": device}
    (credentials / "kimi-code.json").write_text(
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


def write_codex_home(path: Path, *, email: str = "alice@example.com") -> None:
    path.mkdir(parents=True)
    (path / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email, "name": "Test"}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                    "account_id": "acct-1",
                }
            }
        ),
        encoding="utf-8",
    )


def write_claude_home(path: Path, *, email: str = "claude@example.com") -> None:
    path.mkdir(parents=True)
    (path / ".credentials.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": jwt({"email": email}),
                    "expiresAt": 2_000_000_000,
                }
            }
        ),
        encoding="utf-8",
    )
    (path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": email}}),
        encoding="utf-8",
    )


def add(
    runner: CliRunner,
    provider: str,
    home: Path,
    alias: str | None = None,
) -> None:
    args = ["account", "add", "--provider", provider, "--home", str(home)]
    if alias:
        args.extend(["--alias", alias])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output


def test_deploy_uses_project_native_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    source = tmp_path / "source"
    write_kimi_home(source)

    runner = CliRunner()
    add(runner, "kimi", source, "k1")

    result = runner.invoke(cli, ["deploy", "copy", "k1"])
    assert result.exit_code == 0, result.output
    assert f"target: {project / '.kimi-code'}" in result.output
    assert (project / ".kimi-code" / "credentials" / "kimi-code.json").is_file()

    result = runner.invoke(cli, ["deploy", "list", "--json"])
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert len(records) == 1
    assert records[0]["ref"] == "kimi/user-1--device-1"
    assert records[0]["project"] == str(project.resolve())
    assert records[0]["home"] == str((project / ".kimi-code").resolve())
    assert records[0]["state"] == "active"
    assert records[0]["mode"] == "copy"


def test_multiple_homes_in_one_project_are_both_active(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    source_one = tmp_path / "source-one"
    source_two = tmp_path / "source-two"
    write_kimi_home(source_one, device="device-1")
    write_kimi_home(source_two, device="device-2")

    runner = CliRunner()
    add(runner, "kimi", source_one, "k1")
    add(runner, "kimi", source_two, "k2")

    assert runner.invoke(cli, ["deploy", "copy", "k1"]).exit_code == 0
    result = runner.invoke(cli, ["deploy", "copy", "k2", "--home", ".kimi-code-2"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        cli,
        ["deploy", "list", "--group-by", "project", "--active-only", "--json"],
    )
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert {record["ref"] for record in records} == {
        "kimi/user-1--device-1",
        "kimi/user-1--device-2",
    }
    assert {record["home"] for record in records} == {
        str((project / ".kimi-code").resolve()),
        str((project / ".kimi-code-2").resolve()),
    }
    assert {record["state"] for record in records} == {"active"}


def test_overwritten_account_becomes_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    source_one = tmp_path / "source-one"
    source_two = tmp_path / "source-two"
    write_kimi_home(source_one, device="device-1")
    write_kimi_home(source_two, device="device-2")

    runner = CliRunner()
    add(runner, "kimi", source_one, "k1")
    add(runner, "kimi", source_two, "k2")

    assert runner.invoke(cli, ["deploy", "copy", "k1"]).exit_code == 0
    assert runner.invoke(cli, ["deploy", "copy", "k2"]).exit_code == 0

    result = runner.invoke(cli, ["deploy", "list", "--json"])
    records = {record["ref"]: record for record in json.loads(result.output)}
    assert records["kimi/user-1--device-1"]["state"] == "overwritten"
    assert records["kimi/user-1--device-2"]["state"] == "active"

    result = runner.invoke(cli, ["account", "list", "--available", "--json"])
    assert result.exit_code == 0, result.output
    available = json.loads(result.output)
    assert [item["ref"] for item in available] == ["kimi/user-1--device-1"]
    assert available[0]["deployments"][0]["state"] == "overwritten"


def test_never_deployed_account_is_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    source = tmp_path / "source"
    write_kimi_home(source)
    runner = CliRunner()
    add(runner, "kimi", source, "k1")

    result = runner.invoke(cli, ["account", "list", "--available", "--json"])
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert len(records) == 1
    assert records[0]["deployments"] == []


def test_deploy_list_across_kimi_codex_and_claude(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    kimi_source = tmp_path / "kimi-source"
    codex_source = tmp_path / "codex-source"
    claude_source = tmp_path / "claude-source"
    write_kimi_home(kimi_source)
    write_codex_home(codex_source)
    write_claude_home(claude_source)

    runner = CliRunner()
    add(runner, "kimi", kimi_source)
    add(runner, "codex", codex_source)
    add(runner, "claude", claude_source)

    for ref in (
        "kimi/user-1--device-1",
        "codex/alice@example.com",
        "claude/claude@example.com",
    ):
        result = runner.invoke(cli, ["deploy", "copy", ref])
        assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["deploy", "list", "--group-by", "project", "--json"])
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert {record["provider"] for record in records} == {
        "kimi",
        "codex",
        "claude",
    }
    assert {record["home"] for record in records} == {
        str((project / ".kimi-code").resolve()),
        str((project / ".codex").resolve()),
        str((project / ".claude").resolve()),
    }
    assert {record["state"] for record in records} == {"active"}
    assert all(record["project"] == str(project.resolve()) for record in records)


def test_project_filter_and_account_filter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAIREN_HOME", str(tmp_path / "lairen"))
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()
    source = tmp_path / "source"
    write_kimi_home(source)
    runner = CliRunner()
    add(runner, "kimi", source, "k1")

    assert runner.invoke(
        cli, ["deploy", "copy", "k1", "--project", str(project)]
    ).exit_code == 0
    assert runner.invoke(
        cli,
        [
            "deploy",
            "copy",
            "k1",
            "--project",
            str(other),
            "--home",
            ".kimi-code",
        ],
    ).exit_code == 0

    result = runner.invoke(
        cli,
        ["deploy", "list", "--project", str(project), "--json"],
    )
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert len(records) == 1
    assert records[0]["project"] == str(project.resolve())

    result = runner.invoke(cli, ["deploy", "list", "--account", "k1", "--json"])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.output)) == 2
