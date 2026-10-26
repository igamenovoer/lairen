"""Command Code provider (API-key auth)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lairen.errors import LairenError
from lairen.providers.base import Identity, Provider
from lairen.util import sha256_hex


class CommandCodeProvider(Provider):
    name = "commandcode"
    env_var = "COMMANDCODE_HOME"
    tested = False
    deploy_note = "API-key auth; writes the official apiKey shape"
    DEFAULT_HOME = Path.home() / ".commandcode"
    CREDENTIAL_RELPATH = Path("auth.json")

    @staticmethod
    def _key_from_value(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        for field in ("key", "apiKey", "access"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _key_from_live(self, data: dict[str, Any]) -> str | None:
        for field in ("apiKey", "commandcode"):
            candidate = data.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for slot in ("commandcode", "command-code"):
            key = self._key_from_value(data.get(slot))
            if key:
                return key
        return self._key_from_value(data)

    def _key_from_blob(self, blob: str) -> str:
        data = self.load_json(blob)
        key = self._key_from_value(data)
        if not key:
            raise LairenError("commandcode blob has no API key")
        return key

    def read_live(self, home: Path) -> str:
        data = self.load_json(super().read_live(home))
        key = self._key_from_live(data)
        if not key:
            raise LairenError(f"no Command Code API key in {self.credential_path_for(home)}")
        return json.dumps({"type": "api", "key": key})

    def parse_identity(self, home: Path, blob: str) -> Identity:
        key = self._key_from_blob(blob)
        account_id = f"cc-{sha256_hex(key.encode('utf-8'))}"
        suffix = key[-4:] if len(key) >= 4 else key
        return Identity(
            id=account_id,
            label=f"cc-…{suffix}",
            extra={"kind": "api-key", "fingerprint": account_id},
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        key = self._key_from_blob(blob)
        return {
            "kind": "api-key",
            "fingerprint": f"cc-{sha256_hex(key.encode('utf-8'))}",
        }

    def compose(self, existing: str | None, blob: str) -> str:
        return json.dumps({"apiKey": self._key_from_blob(blob)})
