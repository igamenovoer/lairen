"""Explicit, versioned migrations for lairen state."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lairen.deployments import DeploymentLog, project_root_for_home
from lairen.errors import LairenError
from lairen.paths import Paths
from lairen.schema import (
    CURRENT_SCHEMA_VERSION,
    MIN_SUPPORTED_SCHEMA_VERSION,
    check_supported_version,
    legacy_state_present,
    read_schema_version,
    write_schema_version,
)
from lairen.util import atomic_write_text, utc_now


@dataclass
class MigrationReport:
    from_version: int | None
    to_version: int
    fresh: bool = False
    dry_run: bool = False
    deploy_entries: int = 0
    project_filled: int = 0
    legacy_materialized: int = 0
    unattributed: list[tuple[str, str]] = field(default_factory=list)
    backup_path: Path | None = None
    changed: bool = False


def migrate_state(
    paths: Paths,
    project_map: dict[str, str] | None = None,
    *,
    dry_run: bool = False,
    backup: bool = True,
) -> MigrationReport:
    """Migrate lairen state to the current schema version.

    A fresh state is initialized at the current version. Legacy state without
    a schema marker is version 1. Versions below the supported lower bound and
    versions newer than this lairen are rejected.
    """
    mapping = _normalize_map(project_map)
    version = read_schema_version(paths)

    if version is None:
        if not legacy_state_present(paths):
            report = MigrationReport(
                from_version=None,
                to_version=CURRENT_SCHEMA_VERSION,
                fresh=True,
                dry_run=dry_run,
                changed=True,
            )
            if not dry_run:
                write_schema_version(paths, CURRENT_SCHEMA_VERSION)
            return report
        version = MIN_SUPPORTED_SCHEMA_VERSION

    check_supported_version(version)
    if version == CURRENT_SCHEMA_VERSION:
        report = MigrationReport(
            from_version=version,
            to_version=CURRENT_SCHEMA_VERSION,
        )
        if mapping:
            _backfill_current(paths, mapping, report, dry_run=dry_run, backup=backup)
        return report

    report = MigrationReport(
        from_version=version,
        to_version=CURRENT_SCHEMA_VERSION,
        dry_run=dry_run,
        changed=True,
    )
    if version < 2:
        _migrate_v1_to_v2(paths, mapping, report, dry_run=dry_run, backup=backup)

    if not dry_run:
        write_schema_version(paths, CURRENT_SCHEMA_VERSION)
    return report


def _migrate_v1_to_v2(
    paths: Paths,
    project_map: dict[str, str],
    report: MigrationReport,
    *,
    dry_run: bool,
    backup: bool,
) -> None:
    registry = _load_registry(paths.registry_path)
    entries = _load_log(paths.deployments_path)
    log = DeploymentLog(paths.deployments_path)

    if backup and not dry_run:
        report.backup_path = _backup_state(paths)

    _normalize_registry(registry)

    for account in registry:
        provider = str(account["provider"])
        account_id = str(account["id"])
        ref = f"{provider}/{account_id}"
        last_home = account.get("last_deployed_home")
        if not last_home:
            continue
        related = log.related_refs(ref)
        has_deploy = any(
            entry.get("action") == "deploy"
            and str(entry.get("ref") or "") in related
            for entry in entries
        )
        if has_deploy:
            continue
        home = str(Path(str(last_home)).expanduser().resolve())
        entry: dict[str, Any] = {
            "ts": account.get("last_deployed_at") or utc_now(),
            "action": "deploy",
            "provider": provider,
            "ref": ref,
            "project": _project_for(home, project_map),
            "home": home,
            "migrated_from": "last_deployed_home",
        }
        if account.get("alias"):
            entry["alias"] = account["alias"]
        if account.get("source_home"):
            entry["source_home"] = account["source_home"]
        entries.append(entry)
        report.legacy_materialized += 1

    for entry in entries:
        if entry.get("action") != "deploy":
            continue
        report.deploy_entries += 1
        if entry.get("project") is not None:
            continue
        raw_home = entry.get("home")
        if not raw_home:
            entry["project"] = None
            report.unattributed.append((str(entry.get("ref") or ""), ""))
            continue
        home = str(Path(str(raw_home)).expanduser().resolve())
        project = _project_for(home, project_map)
        entry["project"] = project
        if project is None:
            report.unattributed.append((str(entry.get("ref") or ""), home))
        else:
            report.project_filled += 1

    if dry_run:
        return
    if registry or paths.registry_path.exists():
        _write_registry(paths.registry_path, registry)
    if entries or paths.deployments_path.exists():
        _write_log(paths.deployments_path, entries)


def _backfill_current(
    paths: Paths,
    project_map: dict[str, str],
    report: MigrationReport,
    *,
    dry_run: bool,
    backup: bool,
) -> None:
    entries = _load_log(paths.deployments_path)
    changed = False
    for entry in entries:
        if entry.get("action") != "deploy":
            continue
        report.deploy_entries += 1
        raw_home = entry.get("home")
        if entry.get("project") is not None or not raw_home:
            continue
        home = str(Path(str(raw_home)).expanduser().resolve())
        project = project_map.get(home)
        if project is None:
            continue
        entry["project"] = project
        report.project_filled += 1
        changed = True

    for entry in entries:
        if entry.get("action") != "deploy":
            continue
        if entry.get("project") is not None:
            continue
        raw_home = entry.get("home")
        home = str(Path(str(raw_home)).expanduser().resolve()) if raw_home else ""
        report.unattributed.append((str(entry.get("ref") or ""), home))

    if not changed:
        return
    report.changed = True
    if dry_run:
        return
    if backup:
        report.backup_path = _backup_state(paths)
    _write_log(paths.deployments_path, entries)


def _normalize_registry(registry: list[dict[str, Any]]) -> None:
    for account in registry:
        provider = account.get("provider")
        account_id = account.get("id")
        if (
            not isinstance(provider, str)
            or not provider
            or not isinstance(account_id, str)
            or not account_id
        ):
            raise LairenError(
                "registry entry is missing provider/id; "
                "fix it manually or recreate the lairen state"
            )
        if not account.get("label"):
            account["label"] = account_id
        if "source_home" not in account:
            account["source_home"] = ""
        if "alias" not in account:
            account["alias"] = None
        if "created_at" not in account:
            account["created_at"] = utc_now()
        if "last_deployed_at" not in account:
            account["last_deployed_at"] = None
        if "last_deployed_home" not in account:
            account["last_deployed_home"] = None
        if not isinstance(account.get("extra"), dict):
            account["extra"] = {}


def _project_for(home: str, project_map: dict[str, str]) -> str | None:
    if home in project_map:
        return project_map[home]
    parent = project_root_for_home(home)
    if parent is None:
        return None
    parent_path = Path(parent).expanduser().resolve()
    if parent_path == Path.home().expanduser().resolve():
        return None
    return str(parent_path)


def _normalize_map(project_map: dict[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for home, project in (project_map or {}).items():
        result[str(Path(home).expanduser().resolve())] = str(
            Path(project).expanduser().resolve()
        )
    return result


def _load_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LairenError(
            f"cannot read registry {path}: {exc}; "
            "fix it manually or recreate the lairen state"
        ) from exc
    if not isinstance(data, list):
        raise LairenError(
            f"registry {path} is not a JSON list; "
            "fix it manually or recreate the lairen state"
        )
    result: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise LairenError(
                f"registry {path} contains a non-object entry; "
                "fix it manually or recreate the lairen state"
            )
        result.append(item)
    return result


def _load_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LairenError(
                f"deployment log {path} line {number} is invalid: {exc}; "
                "fix it manually or recreate the lairen state"
            ) from exc
        if not isinstance(entry, dict):
            raise LairenError(
                f"deployment log {path} line {number} is not a JSON object; "
                "fix it manually or recreate the lairen state"
            )
        result.append(entry)
    return result


def _write_registry(path: Path, registry: list[dict[str, Any]]) -> None:
    payload = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, payload, mode=0o600)


def _write_log(path: Path, entries: list[dict[str, Any]]) -> None:
    lines = [
        json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        for entry in entries
    ]
    payload = "\n".join(lines) + ("\n" if lines else "")
    atomic_write_text(path, payload, mode=0o600)


def _backup_state(paths: Paths) -> Path | None:
    sources = [
        source
        for source in (
            paths.registry_path,
            paths.deployments_path,
            paths.schema_path,
        )
        if source.exists()
    ]
    if not sources:
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = paths.state_dir / "migrations" / stamp
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for source in sources:
        destination = target / source.name
        shutil.copy2(source, destination)
        os.chmod(destination, 0o600)
    return target
