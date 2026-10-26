"""Directory scanning for Codex and Kimi credential homes."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from lairen.scan import best_per_account, scan_accounts


def b64(value: dict[str, object]) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def write_codex(home: Path, email: str) -> None:
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text(
        json.dumps(
            {
                "tokens": {
                    "id_token": jwt({"email": email}),
                    "access_token": jwt({"exp": 2_000_000_000}),
                }
            }
        ),
        encoding="utf-8",
    )


def write_kimi(home: Path, user_id: str, device_id: str, name: str = "kimi-code.json") -> None:
    credentials = home / ".kimi-code" / "credentials"
    credentials.mkdir(parents=True)
    (credentials / name).write_text(
        json.dumps(
            {
                "access_token": jwt({"user_id": user_id, "device_id": device_id}),
                "refresh_token": jwt({"user_id": user_id, "device_id": device_id}),
                "expires_at": 2_000_000_000,
                "scope": "kimi-code",
            }
        ),
        encoding="utf-8",
    )


def test_depth_and_provider_patterns(tmp_path) -> None:
    root = tmp_path / "workspace"
    write_codex(root / "project-a", "alice@example.com")
    write_kimi(root / "project-b", "user-1", "device-1")
    write_kimi(root / "kimi-slot", "user-2", "device-2", "kimi-code-env-deadbeef.json")
    write_codex(root / "deep" / "level" / "project-c", "bob@example.com")

    depth_one = scan_accounts(root, depth=1)
    assert {hit.ref for hit in depth_one} == {
        "codex/alice@example.com",
        "kimi/user-1--device-1",
        "kimi/user-2--device-2",
    }

    depth_three = scan_accounts(root, depth=3)
    assert {hit.ref for hit in depth_three} == {
        "codex/alice@example.com",
        "codex/bob@example.com",
        "kimi/user-1--device-1",
        "kimi/user-2--device-2",
    }


def test_scan_is_provider_filterable(tmp_path) -> None:
    root = tmp_path / "workspace"
    write_codex(root / "project-a", "alice@example.com")
    write_kimi(root / "project-b", "user-1", "device-1")

    codex_only = scan_accounts(root, depth=1, providers=("codex",))
    assert [hit.ref for hit in codex_only] == ["codex/alice@example.com"]


def test_best_per_account_keeps_newest_copy(tmp_path) -> None:
    root = tmp_path / "workspace"
    write_codex(root / "first", "alice@example.com")
    write_codex(root / "second", "alice@example.com")
    second = root / "second" / ".codex" / "auth.json"
    os.utime(second, (2_000_000_000, 2_000_000_000))
    hits = scan_accounts(root, depth=1)
    assert len(hits) == 2

    best = best_per_account(hits)
    assert len(best) == 1
    assert best[0].credential == second.resolve()
