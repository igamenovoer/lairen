"""Provider abstraction."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import LairenError
from ..util import atomic_write_text


@dataclass
class Identity:
    id: str
    label: str
    extra: dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
    name: str
    env_var: str
    default_home: Path
    credential_relpath: Path

    def resolve_home(self, home: str | None = None) -> Path:
        if home:
            return Path(home).expanduser()
        env_home = os.environ.get(self.env_var)
        if env_home:
            return Path(env_home).expanduser()
        return self.default_home.expanduser()

    def credential_path_for(self, home: Path) -> Path:
        return home / self.credential_relpath

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
        atomic_write_text(path, blob, mode=0o600)
        return path

    @abstractmethod
    def parse_identity(self, blob: str) -> Identity:
        """Extract a stable, non-secret identity from a credential blob."""

    @abstractmethod
    def local_usage(self, blob: str) -> dict[str, Any]:
        """Return local usage metadata; remote quota queries may extend this."""
