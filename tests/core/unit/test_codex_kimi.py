"""Codex and Kimi identity/usage parsing (the tested adapters)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from lairen.providers.codex import CodexProvider
from lairen.providers.kimi import KimiProvider


def b64(value: dict[str, object]) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def test_codex_identity_and_expiry() -> None:
    blob = json.dumps(
        {
            "tokens": {
                "id_token": jwt({"email": "alice@example.com", "name": "Alice"}),
                "access_token": jwt({"exp": 2_000_000_000}),
                "account_id": "acct-1",
            },
            "last_refresh": "2026-10-26T00:00:00Z",
        }
    )
    provider = CodexProvider()
    identity = provider.parse_identity(Path("/tmp/codex"), blob)
    assert identity.id == "alice@example.com"
    assert identity.label == "alice@example.com"
    assert identity.extra["account_id"] == "acct-1"

    usage = provider.local_usage(blob)
    assert usage["access_token_expires_at"] == 2_000_000_000


def test_kimi_identity_is_a_session() -> None:
    claims = {"user_id": "user-1", "device_id": "device-1"}
    blob = json.dumps(
        {
            "access_token": jwt(claims),
            "refresh_token": jwt({**claims, "exp": 2_000_000_100}),
            "expires_at": 2_000_000_000,
            "scope": "kimi-code",
        }
    )
    provider = KimiProvider()
    identity = provider.parse_identity(Path("/tmp/kimi"), blob)
    assert identity.id == "user-1--device-1"
    assert identity.label == "user-1"

    usage = provider.local_usage(blob)
    assert usage["access_token_expires_at"] == 2_000_000_000
    assert usage["refresh_token_expires_at"] == 2_000_000_100
