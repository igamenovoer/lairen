"""Append-only deployment history for project lease reporting."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from lairen.models import Account
from lairen.util import utc_now

PROJECT_HOME_NAMES = (".codex", ".kimi-code", ".claude", ".commandcode", ".opencode")
DEPLOYMENT_ACTIONS = ("deploy", "link")


class _InferProject:
    pass


_INFER_PROJECT = _InferProject()


def project_root_for_home(home: str | Path) -> str | None:
    """Return the project root for a project-local provider home."""
    path = Path(home)
    if path.name in PROJECT_HOME_NAMES:
        return str(path.parent)
    return None


def is_deployment_entry(entry: Mapping[str, object]) -> bool:
    """True for entries that materialize an account in a project home."""
    return entry.get("action") in DEPLOYMENT_ACTIONS


def record_event(
    log_path: Path,
    action: str,
    account: Account,
    *,
    home: str | None = None,
    source_home: str | None = None,
    project: str | Path | None | _InferProject = _INFER_PROJECT,
    previous_ref: str | None = None,
    mode: str | None = None,
) -> None:
    """Append one deployment-history entry, omitting empty fields."""
    home_value = str(Path(home).expanduser().resolve()) if home else None
    source_value = str(Path(source_home).expanduser().resolve()) if source_home else None
    project_value: str | None
    if isinstance(project, _InferProject):
        project_value = project_root_for_home(home_value) if home_value else None
    elif project is None:
        project_value = None
    else:
        project_value = str(Path(project).expanduser().resolve())
    entry: dict[str, object] = {
        "ts": utc_now(),
        "action": action,
        "mode": mode or ("link" if action == "link" else "copy"),
        "provider": account.provider,
        "ref": account.ref,
        "alias": account.alias,
        "project": project_value,
        "home": home_value,
        "source_home": source_value,
        "previous_ref": previous_ref,
    }
    DeploymentLog(log_path).append(
        {
            key: value
            for key, value in entry.items()
            if value is not None or key == "project"
        }
    )


class DeploymentLog:
    """JSON Lines deployment history, stored under the lairen state directory."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, entry: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(entry), ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        os.chmod(self.path, 0o600)

    def entries(self) -> list[dict[str, object]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        result: list[dict[str, object]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                result.append(entry)
        return result

    def leases_for(self, refs: Iterable[str]) -> list[dict[str, object]]:
        """Newest deployment entry per target home for the given account refs."""
        wanted = set(refs)
        latest: dict[str, dict[str, object]] = {}
        for entry in self.entries():
            if not is_deployment_entry(entry):
                continue
            if str(entry.get("ref") or "") not in wanted:
                continue
            home = str(entry.get("home") or "")
            if not home:
                continue
            current = latest.get(home)
            if current is None or str(entry.get("ts") or "") >= str(current.get("ts") or ""):
                latest[home] = entry
        return sorted(
            latest.values(),
            key=lambda item: (str(item.get("ts") or ""), str(item.get("home") or "")),
        )

    def related_refs(self, ref: str) -> set[str]:
        """Follow update entries so a rebind keeps its earlier lease history."""
        refs = {ref}
        changed = True
        while changed:
            changed = False
            for entry in self.entries():
                if entry.get("action") != "update":
                    continue
                current = str(entry.get("ref") or "")
                previous = str(entry.get("previous_ref") or "")
                if not current or not previous:
                    continue
                if current in refs and previous not in refs:
                    refs.add(previous)
                    changed = True
                elif previous in refs and current not in refs:
                    refs.add(current)
                    changed = True
        return refs
