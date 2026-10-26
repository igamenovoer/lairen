"""OpenCode provider (Go API-key slot).

OpenCode Console accounts are metadata-only in the official client and are
switched through its own command; this adapter manages the ``opencode-go``
API-key slot that lives in ``auth.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lairen.errors import LairenError
from lairen.providers.base import Identity, Provider
from lairen.util import sha256_hex

AUTH_SLOT = "opencode-go"


class OpenCodeProvider(Provider):
    name = "opencode"
    env_var = "OPENCODE_HOME"
    tested = False
    deploy_note = "Go API-key slot; Console accounts use the official CLI"
    DEFAULT_HOME = Path.home() / ".local" / "share" / "opencode"
    CREDENTIAL_RELPATH = Path("auth.json")

    def default_home(self) -> Path:
        base = Path(
            os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        ).expanduser()
        return base / "opencode"

    @staticmethod
    def _key_from_entry(entry: Any) -> str | None:
        if not isinstance(entry, dict):
            return None
        key = entry.get("key")
        return key.strip() if isinstance(key, str) and key.strip() else None

    def _key_from_blob(self, blob: str) -> str:
        entry = self.load_json(blob)
        key = self._key_from_entry(entry)
        if not key:
            raise LairenError("opencode blob has no API key")
        return key

    def read_live(self, home: Path) -> str:
        data = self.load_json(super().read_live(home))
        entry = data.get(AUTH_SLOT)
        key = self._key_from_entry(entry)
        if not key:
            raise LairenError(f"no OpenCode Go API key in {self.credential_path_for(home)}")
        return json.dumps({"type": "api", "key": key})

    def parse_identity(self, home: Path, blob: str) -> Identity:
        key = self._key_from_blob(blob)
        account_id = f"go-{sha256_hex(key.encode('utf-8'))}"
        suffix = key[-4:] if len(key) >= 4 else key
        return Identity(
            id=account_id,
            label=f"sk-…{suffix}",
            extra={"kind": "api-key", "fingerprint": account_id},
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        key = self._key_from_blob(blob)
        return {
            "kind": "api-key",
            "fingerprint": f"go-{sha256_hex(key.encode('utf-8'))}",
        }

    def compose(self, existing: str | None, blob: str) -> str:
        data: dict[str, Any] = {}
        if existing:
            try:
                loaded = json.loads(existing)
                if isinstance(loaded, dict):
                    data = loaded
            except json.JSONDecodeError:
                data = {}
        data[AUTH_SLOT] = self.load_json(blob)
        return json.dumps(data)
