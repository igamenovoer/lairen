"""Schema versions for the on-disk lairen state."""

from __future__ import annotations

import json

from lairen.errors import LairenError
from lairen.paths import Paths
from lairen.util import atomic_write_text

CURRENT_SCHEMA_VERSION = 3
MIN_SUPPORTED_SCHEMA_VERSION = 1


def read_schema_version(paths: Paths) -> int | None:
    """Return the recorded schema version, or None when no marker exists."""
    path = paths.schema_path
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LairenError(
            f"cannot read schema marker {path}: {exc}; "
            "run `lairen migrate` or recreate the lairen state"
        ) from exc
    if not isinstance(data, dict):
        raise LairenError(
            f"schema marker {path} is not a JSON object; "
            "run `lairen migrate` or recreate the lairen state"
        )
    version = data.get("version")
    if not isinstance(version, int):
        raise LairenError(
            f"schema marker {path} has no integer version; "
            "run `lairen migrate` or recreate the lairen state"
        )
    return version


def write_schema_version(paths: Paths, version: int) -> None:
    payload = json.dumps({"version": version}, indent=2) + "\n"
    atomic_write_text(paths.schema_path, payload, mode=0o600)


def legacy_state_present(paths: Paths) -> bool:
    """True when state files exist without a schema marker."""
    return any(
        path.exists()
        for path in (
            paths.registry_path,
            paths.credentials_path,
            paths.deployments_path,
        )
    )


def require_current_schema(paths: Paths, *, initialize: bool = True) -> None:
    """Reject unmigrated, unsupported, or older state.

    A completely fresh state gets the current marker when ``initialize`` is
    true. Existing state must be migrated explicitly, even when its version is
    still supported by lower-level migration code.
    """
    version = read_schema_version(paths)
    if version is None:
        if legacy_state_present(paths):
            raise LairenError(
                "legacy lairen state detected (no schema marker); "
                "run `lairen migrate` before using this command"
            )
        if initialize:
            write_schema_version(paths, CURRENT_SCHEMA_VERSION)
        return
    check_supported_version(version)
    if version != CURRENT_SCHEMA_VERSION:
        raise LairenError(
            f"lairen state schema v{version} requires migration; "
            f"run `lairen migrate` to upgrade to v{CURRENT_SCHEMA_VERSION}"
        )


def check_supported_version(version: int) -> None:
    if version < MIN_SUPPORTED_SCHEMA_VERSION:
        raise LairenError(
            f"lairen state schema v{version} is below the minimum supported "
            f"v{MIN_SUPPORTED_SCHEMA_VERSION}; migrate it manually or recreate "
            "the lairen state"
        )
    if version > CURRENT_SCHEMA_VERSION:
        raise LairenError(
            f"lairen state schema v{version} is newer than this lairen "
            f"(v{CURRENT_SCHEMA_VERSION}); upgrade lairen"
        )


def schema_status(paths: Paths) -> str:
    """Describe the schema without failing, for diagnostics."""
    version = read_schema_version(paths)
    if version is None:
        if legacy_state_present(paths):
            return f"legacy (no marker; run `lairen migrate`; current v{CURRENT_SCHEMA_VERSION})"
        return f"fresh (current v{CURRENT_SCHEMA_VERSION})"
    if version < MIN_SUPPORTED_SCHEMA_VERSION:
        return (
            f"v{version} (below minimum v{MIN_SUPPORTED_SCHEMA_VERSION}; "
            "manual migration required)"
        )
    if version > CURRENT_SCHEMA_VERSION:
        return f"v{version} (newer than lairen v{CURRENT_SCHEMA_VERSION}; upgrade lairen)"
    if version < CURRENT_SCHEMA_VERSION:
        return f"v{version} (migration required; run `lairen migrate`)"
    return f"v{version}"
