"""Codex / ChatGPT provider."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lairen.providers.base import Identity, Provider
from lairen.util import epoch_to_iso, parse_jwt_claims


class CodexProvider(Provider):
    name = "codex"
    env_var = "CODEX_HOME"
    tested = True
    DEFAULT_HOME = Path.home() / ".codex"
    CREDENTIAL_RELPATH = Path("auth.json")

    def parse_identity(self, home: Path, blob: str) -> Identity:
        data = self.load_json(blob)
        tokens = data.get("tokens") or {}
        claims = parse_jwt_claims(tokens.get("id_token"))
        email = claims.get("email") or data.get("email")
        account_id = tokens.get("account_id") or claims.get("sub")
        name = claims.get("name")
        account_key = data.get("account_key")
        identity = account_key or email or account_id
        if not identity:
            digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
            identity = f"codex-{digest}"
        return Identity(
            id=str(identity),
            label=str(email or name or identity),
            extra={
                "email": email,
                "account_id": account_id,
                "name": name,
            },
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        data = self.load_json(blob)
        tokens = data.get("tokens") or {}
        access_claims = parse_jwt_claims(tokens.get("access_token"))
        id_claims = parse_jwt_claims(tokens.get("id_token"))
        expires_at = access_claims.get("exp")
        return {
            "email": id_claims.get("email"),
            "account_id": tokens.get("account_id"),
            "name": id_claims.get("name"),
            "last_refresh": data.get("last_refresh"),
            "access_token_expires_at": expires_at,
            "access_token_expires_iso": epoch_to_iso(expires_at),
        }
