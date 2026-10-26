"""Registry and credential store behavior."""

from __future__ import annotations

import os
import stat

import pytest

from lairen.errors import LairenError
from lairen.models import Account
from lairen.store import CredentialStore, Registry


def test_registry_roundtrip_and_resolution(tmp_path) -> None:
    registry = Registry(tmp_path / "registry.json")
    account = Account(
        provider="codex",
        id="alice@example.com",
        label="alice@example.com",
        source_home="/tmp/codex",
    )
    registry.upsert(account)

    assert registry.get("codex", "alice@example.com") == account
    assert registry.resolve("codex/alice@example.com") == account
    assert registry.resolve("alice@example.com") == account

    registry.remove("codex", "alice@example.com")
    assert registry.list() == []
    with pytest.raises(LairenError):
        registry.resolve("alice@example.com")


def test_registry_rejects_ambiguous_bare_id(tmp_path) -> None:
    registry = Registry(tmp_path / "registry.json")
    registry.upsert(Account("codex", "id-1", "same", "/tmp/a"))
    registry.upsert(Account("kimi", "id-2", "same", "/tmp/b"))
    with pytest.raises(LairenError, match="ambiguous"):
        registry.resolve("same")


def test_credential_store_roundtrip_and_mode(tmp_path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.set("codex", "alice@example.com", '{"tokens": {}}')
    assert store.get("codex", "alice@example.com") == '{"tokens": {}}'
    assert store.count() == 1

    if os.name == "posix":
        mode = stat.S_IMODE((tmp_path / "credentials.json").stat().st_mode)
        assert mode == 0o600

    assert store.delete("codex", "alice@example.com") is True
    assert store.get("codex", "alice@example.com") is None
