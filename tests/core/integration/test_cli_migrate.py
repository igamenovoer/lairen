"""CLI behavior of the explicit state migration."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lairen.cli import cli
from lairen.schema import CURRENT_SCHEMA_VERSION


def legacy_root(tmp_path: Path) -> Path:
    root = tmp_path / "lairen"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    return root


def write_legacy_state(root: Path, *, custom_home: Path | None = None) -> None:
    accounts = [
        {
            "provider": "kimi",
            "id": "user-1--device-1",
            "label": "user-1",
            "source_home": "/source",
            "alias": "k1",
            "extra": {},
        }
    ]
    (root / "config" / "registry.json").write_text(
        json.dumps(accounts, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "data" / "credentials.json").write_text("{}\n", encoding="utf-8")
    entries = [
        {
            "ts": "2026-11-01T00:00:00+00:00",
            "action": "deploy",
            "provider": "kimi",
            "ref": "kimi/user-1--device-1",
            "alias": "k1",
            "home": str(custom_home or (root / "project" / ".kimi-code")),
        }
    ]
    (root / "state" / "deployments.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )


def test_legacy_state_blocks_commands_until_migrated(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    write_legacy_state(root)

    result = CliRunner().invoke(cli, ["list"])

    assert result.exit_code == 1
    assert "lairen migrate" in result.output


def test_migrate_dry_run_then_apply(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    write_legacy_state(root)
    runner = CliRunner()

    result = runner.invoke(cli, ["migrate", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "schema: v1 -> v2" in result.output
    assert "dry run: no files written" in result.output
    assert not (root / "data" / "schema.json").exists()

    result = runner.invoke(cli, ["migrate"])
    assert result.exit_code == 0, result.output
    assert "schema: v1 -> v2" in result.output
    schema = json.loads((root / "data" / "schema.json").read_text(encoding="utf-8"))
    assert schema["version"] == CURRENT_SCHEMA_VERSION
    backups = list((root / "state" / "migrations").iterdir())
    assert len(backups) == 1
    assert (backups[0] / "registry.json").is_file()
    assert (backups[0] / "deployments.jsonl").is_file()

    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0, result.output
    assert "kimi/user-1--device-1" in result.output

    result = runner.invoke(cli, ["migrate"])
    assert result.exit_code == 0, result.output
    assert "nothing to migrate" in result.output


def test_migrate_attributes_custom_home_with_project_option(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    project = tmp_path / "project"
    custom_home = project / ".kimi-alt"
    write_legacy_state(root, custom_home=custom_home)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["migrate", "--project", f"{custom_home}={project}"],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["associations", "--json"])
    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    assert len(records) == 1
    assert records[0]["project"] == str(project.resolve())


def test_migrate_reports_unattributed_custom_home(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    custom_home = tmp_path / "project" / ".kimi-alt"
    write_legacy_state(root, custom_home=custom_home)

    result = CliRunner().invoke(cli, ["migrate"])

    assert result.exit_code == 0, result.output
    assert "unattributed   : 1" in result.output
    assert str(custom_home) in result.output


def test_migrate_applies_a_late_mapping_on_current_state(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    project = tmp_path / "project"
    custom_home = project / ".kimi-alt"
    write_legacy_state(root, custom_home=custom_home)
    runner = CliRunner()
    assert runner.invoke(cli, ["migrate"]).exit_code == 0

    result = runner.invoke(
        cli,
        ["migrate", "--project", f"{custom_home}={project}"],
    )

    assert result.exit_code == 0, result.output
    assert "schema: v2 (current)" in result.output
    assert "project filled : 1" in result.output
    records = json.loads(runner.invoke(cli, ["associations", "--json"]).output)
    assert records[0]["project"] == str(project.resolve())


def test_migrate_rejects_below_minimum_version(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    (root / "data" / "schema.json").write_text(
        json.dumps({"version": 0}) + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["migrate"])

    assert result.exit_code == 1
    assert "below the minimum supported" in result.output


def test_migrate_rejects_newer_version(tmp_path, monkeypatch) -> None:
    root = legacy_root(tmp_path)
    monkeypatch.setenv("LAIREN_HOME", str(root))
    (root / "data" / "schema.json").write_text(
        json.dumps({"version": CURRENT_SCHEMA_VERSION + 1}) + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["migrate"])

    assert result.exit_code == 1
    assert "newer than this lairen" in result.output
