"""Schema marker detection and version bounds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lairen.errors import LairenError
from lairen.paths import Paths
from lairen.schema import (
    CURRENT_SCHEMA_VERSION,
    MIN_SUPPORTED_SCHEMA_VERSION,
    read_schema_version,
    require_current_schema,
    schema_status,
    write_schema_version,
)


def make_paths(tmp_path: Path) -> Paths:
    return Paths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
    )


def test_fresh_state_gets_the_current_marker(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()

    require_current_schema(paths)

    assert read_schema_version(paths) == CURRENT_SCHEMA_VERSION
    assert paths.schema_path.is_file()


def test_read_only_check_does_not_create_a_marker(tmp_path) -> None:
    paths = make_paths(tmp_path)

    require_current_schema(paths, initialize=False)

    assert not paths.schema_path.exists()
    assert not paths.data_dir.exists()


def test_legacy_state_without_a_marker_requires_migration(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    paths.registry_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(LairenError, match="lairen migrate"):
        require_current_schema(paths)

    assert not paths.schema_path.exists()


def test_version_below_the_minimum_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    write_schema_version(paths, MIN_SUPPORTED_SCHEMA_VERSION - 1)

    with pytest.raises(LairenError, match="below the minimum supported"):
        require_current_schema(paths)


def test_version_newer_than_lairen_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    write_schema_version(paths, CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(LairenError, match="newer than this lairen"):
        require_current_schema(paths)


def test_malformed_marker_is_rejected(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    paths.schema_path.write_text(json.dumps({"version": "two"}), encoding="utf-8")

    with pytest.raises(LairenError, match="integer version"):
        read_schema_version(paths)


def test_schema_status_does_not_raise_for_legacy_state(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    paths.registry_path.write_text("[]\n", encoding="utf-8")

    assert "legacy" in schema_status(paths)


def test_supported_older_state_still_requires_migration(tmp_path) -> None:
    paths = make_paths(tmp_path).ensure()
    write_schema_version(paths, CURRENT_SCHEMA_VERSION - 1)

    with pytest.raises(LairenError, match="requires migration"):
        require_current_schema(paths)

    assert "migration required" in schema_status(paths)
