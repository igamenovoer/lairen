"""Resolved configuration, data, and state locations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    data_dir: Path
    state_dir: Path

    @classmethod
    def resolve(cls) -> "Paths":
        root = os.environ.get("LAIREN_HOME")
        if root:
            base = Path(root).expanduser().resolve()
            return cls(base / "config", base / "data", base / "state")

        config_base = Path(
            os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ).expanduser()
        data_base = Path(
            os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        ).expanduser()
        data_dir = data_base / "lairen"
        return cls(config_base / "lairen", data_dir, data_dir / "state")

    def ensure(self) -> "Paths":
        for directory in (self.config_dir, self.data_dir, self.state_dir):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self

    @property
    def registry_path(self) -> Path:
        return self.config_dir / "registry.json"

    @property
    def credentials_path(self) -> Path:
        return self.data_dir / "credentials.json"

    @property
    def snapshots_dir(self) -> Path:
        return self.state_dir / "snapshots"
