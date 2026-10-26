"""Append-only deployment history for project lease reporting."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

PROJECT_HOME_NAMES = (".codex", ".kimi-code", ".claude", ".commandcode")


def project_root_for_home(home: str | Path) -> str | None:
    """Return the project root for a project-local provider home."""
    path = Path(home)
    if path.name in PROJECT_HOME_NAMES:
        return str(path.parent)
    return None


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
        """Newest deploy entry per target home for the given account refs."""
        wanted = set(refs)
        latest: dict[str, dict[str, object]] = {}
        for entry in self.entries():
            if entry.get("action") != "deploy":
                continue
            if str(entry.get("ref") or "") not in wanted:
                continue
            home = str(entry.get("home") or "")
            if not home:
                continue
            current = latest.get(home)
            if current is None or str(entry.get("ts") or "") >= str(
                current.get("ts") or ""
            ):
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
