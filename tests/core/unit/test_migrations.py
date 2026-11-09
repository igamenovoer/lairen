"""Explicit state migrations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lairen.associations import build_associations
from lairen.deployments import DeploymentLog
from lairen.errors import LairenError
from lairen.migrations import migrate_state
from lairen.paths import Paths
from lairen.schema import CURRENT_SCHEMA_VERSION, read_schema_version, write_schema_version
from lairen.store import Registry


def make_paths(tmp_path: Path) -> Paths:
    return Paths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
    ).ensure()


def write_registry(paths: Paths, accounts: list[dict[str, object]]) -> None:
    paths.registry_path.write_text(
        json.dumps(accounts, indent=2) + "\n",
        encoding="utf-8",
    )


def write_log(paths: Paths, entries: list[dict[str, object]]) -> None:
    text = "".join(
        json.dumps(entry, separators=(",", ":")) + "\n" for entry in entries
    )
    paths.deployments_path.write_text(text, encoding="utf-8")


def account(
    provider: str,
    account_id: str,
    *,
    alias: str | None = None,
    last_home: str | None = None,
    last_at: str | None = None,
) -> dict[str, object]:
    return {
        "provider": provider,
        "id": account_id,
        "label": account_id,
        "source_home": f"/source/{account_id}",
        "alias": alias,
        "last_deployed_at": last_at,
        "last_deployed_home": last_home,
        "extra": {},
    }


def test_migrates_legacy_pointer_into_a_deploy_entry(tmp_path) -> None:
    paths = make_paths(tmp_path)
    home = tmp_path / "project" / ".codex"
    write_registry(
        paths,
        [
            account(
                "codex",
                "alice@example.com",
                alias="alice",
                last_home=str(home),
                last_at="2026-11-01T00:00:00+00:00",
            )
        ],
    )

    report = migrate_state(paths)

    assert report.from_version == 1
    assert report.to_version == CURRENT_SCHEMA_VERSION
    assert report.legacy_materialized == 1
    assert read_schema_version(paths) == CURRENT_SCHEMA_VERSION
    assert report.backup_path is not None
    assert report.backup_path.is_dir()

    entries = DeploymentLog(paths.deployments_path).entries()
    assert len(entries) == 1
    assert entries[0]["action"] == "deploy"
    assert entries[0]["home"] == str(home.resolve())
    assert entries[0]["project"] == str((tmp_path / "project").resolve())
    assert entries[0]["migrated_from"] == "last_deployed_home"

    associations = build_associations(
        Registry(paths.registry_path).list(),
        DeploymentLog(paths.deployments_path),
    )
    assert len(associations) == 1
    assert associations[0].state == "active"
    assert associations[0].project == str((tmp_path / "project").resolve())


def test_fills_standard_projects_and_reports_unattributed_entries(tmp_path) -> None:
    paths = make_paths(tmp_path)
    project = tmp_path / "project"
    custom_home = project / ".kimi-alt"
    write_registry(
        paths,
        [
            account("codex", "alice@example.com"),
            account("kimi", "user-1--device-1"),
        ],
    )
    write_log(
        paths,
        [
            {
                "ts": "2026-11-01T00:00:00+00:00",
                "action": "deploy",
                "provider": "codex",
                "ref": "codex/alice@example.com",
                "home": str(project / ".codex"),
            },
            {
                "ts": "2026-11-01T01:00:00+00:00",
                "action": "deploy",
                "provider": "kimi",
                "ref": "kimi/user-1--device-1",
                "home": str(custom_home),
            },
        ],
    )

    report = migrate_state(paths)

    assert report.project_filled == 1
    assert report.unattributed == [
        ("kimi/user-1--device-1", str(custom_home.resolve()))
    ]
    entries = DeploymentLog(paths.deployments_path).entries()
    assert entries[0]["project"] == str(project.resolve())
    assert entries[1]["project"] is None


def test_explicit_project_map_attributes_custom_homes(tmp_path) -> None:
    paths = make_paths(tmp_path)
    project = tmp_path / "project"
    custom_home = project / ".kimi-alt"
    write_registry(paths, [account("kimi", "user-1--device-1")])
    write_log(
        paths,
        [
            {
                "ts": "2026-11-01T00:00:00+00:00",
                "action": "deploy",
                "provider": "kimi",
                "ref": "kimi/user-1--device-1",
                "home": str(custom_home),
            }
        ],
    )

    report = migrate_state(paths, {str(custom_home): str(project)})

    assert report.project_filled == 1
    assert report.unattributed == []
    entries = DeploymentLog(paths.deployments_path).entries()
    assert entries[0]["project"] == str(project.resolve())


def test_current_state_accepts_a_late_project_mapping(tmp_path) -> None:
    paths = make_paths(tmp_path)
    project = tmp_path / "project"
    custom_home = project / ".kimi-alt"
    write_registry(paths, [account("kimi", "user-1--device-1")])
    write_log(
        paths,
        [
            {
                "ts": "2026-11-01T00:00:00+00:00",
                "action": "deploy",
                "provider": "kimi",
                "ref": "kimi/user-1--device-1",
                "home": str(custom_home),
            }
        ],
    )

    first = migrate_state(paths)
    assert first.unattributed == [
        ("kimi/user-1--device-1", str(custom_home.resolve()))
    ]

    second = migrate_state(paths, {str(custom_home): str(project)})
    assert second.from_version == CURRENT_SCHEMA_VERSION
    assert second.project_filled == 1
    assert second.changed is True

    entries = DeploymentLog(paths.deployments_path).entries()
    assert entries[0]["project"] == str(project.resolve())


def test_dry_run_writes_nothing(tmp_path) -> None:
    paths = make_paths(tmp_path)
    project = tmp_path / "project"
    write_registry(paths, [account("codex", "alice@example.com")])
    write_log(
        paths,
        [
            {
                "ts": "2026-11-01T00:00:00+00:00",
                "action": "deploy",
                "provider": "codex",
                "ref": "codex/alice@example.com",
                "home": str(project / ".codex"),
            }
        ],
    )
    before = paths.deployments_path.read_text(encoding="utf-8")

    report = migrate_state(paths, dry_run=True)

    assert report.project_filled == 1
    assert not paths.schema_path.exists()
    assert paths.deployments_path.read_text(encoding="utf-8") == before
    assert not (paths.state_dir / "migrations").exists()


def test_migrate_is_idempotent(tmp_path) -> None:
    paths = make_paths(tmp_path)
    write_registry(paths, [account("codex", "alice@example.com")])

    first = migrate_state(paths)
    second = migrate_state(paths)

    assert first.from_version == 1
    assert first.changed is True
    assert second.from_version == CURRENT_SCHEMA_VERSION
    assert second.changed is False


def test_below_minimum_version_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path)
    write_schema_version(paths, 0)

    with pytest.raises(LairenError, match="below the minimum supported"):
        migrate_state(paths)


def test_newer_version_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path)
    write_schema_version(paths, CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(LairenError, match="newer than this lairen"):
        migrate_state(paths)


def test_fresh_state_is_initialized(tmp_path) -> None:
    paths = make_paths(tmp_path)

    report = migrate_state(paths)

    assert report.fresh is True
    assert report.to_version == CURRENT_SCHEMA_VERSION
    assert read_schema_version(paths) == CURRENT_SCHEMA_VERSION


def test_malformed_log_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path)
    paths.deployments_path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(LairenError, match="line 1 is invalid"):
        migrate_state(paths)
