"""Resolve a deploy target home and its project attribution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lairen.deployments import project_root_for_home
from lairen.errors import LairenError
from lairen.providers import PROVIDERS
from lairen.providers.base import Provider


@dataclass(frozen=True)
class DeployTarget:
    """A provider home plus the project it is attributed to, if any."""

    project: Path | None
    home: Path


def resolve_deploy_target(
    provider: Provider,
    project: str | Path | None = None,
    home: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> DeployTarget:
    """Resolve ``--project``/``--home`` into an absolute home and project.

    A missing ``--home`` uses the provider's native project home name. A
    relative ``--home`` resolves under ``--project`` or the current directory.
    """
    current = (
        Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd().resolve()
    )
    explicit_project = (
        Path(project).expanduser().resolve() if project is not None else None
    )

    if home is None:
        native_name = provider.PROJECT_HOME_NAME
        if native_name is None:
            raise LairenError(
                f"{provider.name} has no default project home; pass --home"
            )
        root = explicit_project or current
        target = (root / native_name).resolve()
        _validate_home_shape(provider, target)
        return DeployTarget(project=root, home=target)

    home_path = Path(home).expanduser()
    if home_path.is_absolute():
        target = home_path.resolve()
    else:
        base = explicit_project or current
        target = (base / home_path).resolve()

    _validate_home_shape(provider, target)
    return DeployTarget(
        project=_infer_project(target, explicit_project, current),
        home=target,
    )


def foreign_home_warning(provider: Provider, home: Path) -> str | None:
    """Return a warning when ``home`` looks like another provider's home."""
    for other in PROVIDERS.values():
        if other.name == provider.name or not other.PROJECT_HOME_NAME:
            continue
        if home.name == other.PROJECT_HOME_NAME:
            return (
                f"target {home} uses the {other.name} home name "
                f"but holds a {provider.name} account"
            )
    return None


def _infer_project(
    target: Path,
    explicit_project: Path | None,
    current: Path,
) -> Path | None:
    if explicit_project is not None:
        return explicit_project
    if _is_relative_to(target, current):
        return current
    parent = project_root_for_home(target)
    if parent is not None:
        parent_path = Path(parent).expanduser().resolve()
        if parent_path != Path.home().expanduser().resolve():
            return parent_path
    return None


def _validate_home_shape(provider: Provider, target: Path) -> None:
    if target.exists() and target.is_file():
        raise LairenError(
            f"--home must be a provider home directory, not a file: {target}"
        )
    if target.name == provider.CREDENTIAL_RELPATH.name:
        raise LairenError(
            f"--home must be a provider home directory, not a credential file: {target}"
        )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
