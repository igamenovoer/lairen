"""Deploy target resolution and project attribution."""

from __future__ import annotations

import pytest

from lairen.errors import LairenError
from lairen.providers import get_provider
from lairen.targets import foreign_home_warning, resolve_deploy_target


def test_native_home_name_under_project(tmp_path) -> None:
    project = tmp_path / "project"
    target = resolve_deploy_target(
        get_provider("kimi"),
        project=project,
        home=None,
        cwd=tmp_path,
    )

    assert target.project == project.resolve()
    assert target.home == (project / ".kimi-code").resolve()


def test_both_omitted_uses_current_directory(tmp_path) -> None:
    target = resolve_deploy_target(
        get_provider("codex"),
        project=None,
        home=None,
        cwd=tmp_path,
    )

    assert target.project == tmp_path.resolve()
    assert target.home == (tmp_path / ".codex").resolve()


def test_relative_home_resolves_under_project(tmp_path) -> None:
    project = tmp_path / "project"
    target = resolve_deploy_target(
        get_provider("kimi"),
        project=project,
        home=".kimi-code-2",
        cwd=tmp_path,
    )

    assert target.project == project.resolve()
    assert target.home == (project / ".kimi-code-2").resolve()


def test_relative_home_without_project_uses_cwd(tmp_path) -> None:
    target = resolve_deploy_target(
        get_provider("codex"),
        project=None,
        home="worker/.codex",
        cwd=tmp_path,
    )

    assert target.project == tmp_path.resolve()
    assert target.home == (tmp_path / "worker" / ".codex").resolve()


def test_absolute_home_inside_cwd_is_attributed(tmp_path) -> None:
    home = tmp_path / "project" / ".kimi-worker"
    target = resolve_deploy_target(
        get_provider("kimi"),
        project=None,
        home=home,
        cwd=tmp_path,
    )

    assert target.project == tmp_path.resolve()
    assert target.home == home.resolve()


def test_absolute_standard_home_outside_cwd_uses_parent(tmp_path) -> None:
    outside = tmp_path / "other" / ".codex"
    target = resolve_deploy_target(
        get_provider("codex"),
        project=None,
        home=outside,
        cwd=tmp_path / "cwd",
    )

    assert target.project == (tmp_path / "other").resolve()
    assert target.home == outside.resolve()


def test_absolute_custom_home_outside_cwd_is_unattributed(tmp_path) -> None:
    outside = tmp_path / "other" / ".kimi-worker-a"
    target = resolve_deploy_target(
        get_provider("kimi"),
        project=None,
        home=outside,
        cwd=tmp_path / "cwd",
    )

    assert target.project is None
    assert target.home == outside.resolve()


def test_cursor_requires_an_explicit_home(tmp_path) -> None:
    with pytest.raises(LairenError, match="no default project home"):
        resolve_deploy_target(
            get_provider("cursor"),
            project=tmp_path / "project",
            home=None,
            cwd=tmp_path,
        )


def test_credential_file_is_rejected_as_home(tmp_path) -> None:
    credential = tmp_path / "project" / ".kimi-code" / "credentials" / "kimi-code.json"
    with pytest.raises(LairenError, match="credential file"):
        resolve_deploy_target(
            get_provider("kimi"),
            project=None,
            home=credential,
            cwd=tmp_path,
        )


def test_existing_file_is_rejected_as_home(tmp_path) -> None:
    path = tmp_path / "not-a-home"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(LairenError, match="not a file"):
        resolve_deploy_target(
            get_provider("kimi"),
            project=None,
            home=path,
            cwd=tmp_path,
        )


def test_foreign_home_name_warns(tmp_path) -> None:
    warning = foreign_home_warning(get_provider("kimi"), tmp_path / ".codex")
    assert warning is not None
    assert "codex" in warning

    assert foreign_home_warning(get_provider("kimi"), tmp_path / ".kimi-code") is None
