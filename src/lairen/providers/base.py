"""Provider abstraction shared by every CLI agent adapter."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lairen.errors import LairenError
from lairen.util import atomic_write_text


@dataclass
class Identity:
    id: str
    label: str
    extra: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    """A credential source that can be saved and deployed into a target home."""

    name: str
    env_var: str | None = None
    tested: bool = False
    deploy_note: str = ""
    DEFAULT_HOME: Path
    CREDENTIAL_RELPATH: Path

    def default_home(self) -> Path:
        return self.DEFAULT_HOME

    def resolve_home(self, home: str | Path | None = None) -> Path:
        if home:
            return Path(home).expanduser()
        if self.env_var:
            env_home = os.environ.get(self.env_var)
            if env_home:
                return Path(env_home).expanduser()
        return self.default_home().expanduser()

    def credential_path_for(self, home: Path) -> Path:
        return home / self.CREDENTIAL_RELPATH

    def read_live(self, home: Path) -> str:
        path = self.credential_path_for(home)
        if not path.is_file():
            raise LairenError(f"no {self.name} login at {path}")
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LairenError(f"cannot read {path}: {exc}") from exc

    def write_live(self, home: Path, blob: str) -> Path:
        path = self.credential_path_for(home)
        text = blob if blob.endswith("\n") else blob + "\n"
        atomic_write_text(path, text, mode=0o600)
        return path

    def compose(self, existing: str | None, blob: str) -> str:
        """Merge a saved blob into the current target file. Defaults to replacement."""
        return blob

    def deploy(self, home: Path, blob: str) -> Path:
        path = self.credential_path_for(home)
        existing = None
        if path.is_file():
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise LairenError(f"cannot read {path}: {exc}") from exc
        return self.write_live(home, self.compose(existing, blob))

    def load_json(self, blob: str) -> dict[str, Any]:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise LairenError(f"{self.name} credential is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LairenError(f"{self.name} credential must be a JSON object")
        return data

    @abstractmethod
    def parse_identity(self, home: Path, blob: str) -> Identity:
        """Extract a stable, non-secret identity from a saved credential blob."""

    @abstractmethod
    def local_usage(self, blob: str) -> dict[str, Any]:
        """Return local usage metadata. Remote quota queries can extend this later."""
