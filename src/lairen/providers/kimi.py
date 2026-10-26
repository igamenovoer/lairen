"""Kimi Code provider.

Kimi identities are sessions: ``user_id`` plus ``device_id``.  Two logins of
the same account are distinct, separately deployable units, so the account id
is ``user_id--device_id`` rather than just ``user_id``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..errors import LairenError
from ..util import epoch_to_iso, parse_jwt_claims
from .base import Identity, Provider


class KimiProvider(Provider):
    name = "kimi"
    env_var = "KIMI_CODE_HOME"
    default_home = Path.home() / ".kimi-code"
    credential_relpath = Path("credentials/kimi-code.json")

    def parse_identity(self, blob: str) -> Identity:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise LairenError(f"kimi credential is not valid JSON: {exc}") from exc
        claims = parse_jwt_claims(data.get("access_token"))
        if not claims:
            claims = parse_jwt_claims(data.get("refresh_token"))
        user_id = claims.get("user_id") or claims.get("sub")
        device_id = claims.get("device_id")
        if not user_id:
            digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
            user_id = f"kimi-{digest}"
        identity = f"{user_id}--{device_id}" if device_id else str(user_id)
        return Identity(
            id=identity,
            label=str(user_id),
            extra={
                "user_id": user_id,
                "device_id": device_id,
                "scope": data.get("scope"),
            },
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise LairenError(f"kimi credential is not valid JSON: {exc}") from exc
        access_claims = parse_jwt_claims(data.get("access_token"))
        refresh_claims = parse_jwt_claims(data.get("refresh_token"))
        expires_at = data.get("expires_at") or access_claims.get("exp")
        return {
            "user_id": access_claims.get("user_id") or access_claims.get("sub"),
            "device_id": access_claims.get("device_id"),
            "scope": data.get("scope"),
            "token_type": data.get("token_type"),
            "access_token_expires_at": expires_at,
            "access_token_expires_iso": epoch_to_iso(expires_at),
            "refresh_token_expires_at": refresh_claims.get("exp"),
            "refresh_token_expires_iso": epoch_to_iso(refresh_claims.get("exp")),
        }
