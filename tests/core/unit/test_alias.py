"""Account alias storage, validation, and resolution."""

from __future__ import annotations

import pytest

from lairen.errors import LairenError
from lairen.models import Account
from lairen.store import Registry


def make_registry(tmp_path) -> Registry:
    registry = Registry(tmp_path / "registry.json")
    registry.upsert(Account("kimi", "user-1--device-1", "user-1", "/tmp/h1"))
    registry.upsert(Account("kimi", "user-1--device-2", "user-1", "/tmp/h2"))
    registry.upsert(
        Account("codex", "alice@example.com", "alice@example.com", "/tmp/h3")
    )
    return registry


def test_alias_resolves_before_a_shared_label(tmp_path) -> None:
    registry = make_registry(tmp_path)
    registry.set_alias("kimi", "user-1--device-1", "kimi-a")

    assert registry.resolve("kimi-a").id == "user-1--device-1"
    with pytest.raises(LairenError, match="ambiguous"):
        registry.resolve("user-1")


def test_alias_validation_rejects_invalid_names(tmp_path) -> None:
    registry = make_registry(tmp_path)
    with pytest.raises(LairenError, match="must start"):
        registry.validate_alias("-leading-dash")
    with pytest.raises(LairenError, match="must start"):
        registry.validate_alias("has space")
    with pytest.raises(LairenError, match="must start"):
        registry.validate_alias("has/slash")
    with pytest.raises(LairenError, match="must start"):
        registry.validate_alias("x" * 65)


def test_alias_rejects_conflicts_with_ids_labels_and_other_aliases(tmp_path) -> None:
    registry = make_registry(tmp_path)
    with pytest.raises(LairenError, match="conflicts with account id"):
        registry.validate_alias("alice@example.com", "kimi", "user-1--device-1")
    with pytest.raises(LairenError, match="conflicts with label"):
        registry.validate_alias("user-1", "codex", "alice@example.com")

    registry.set_alias("kimi", "user-1--device-1", "shared")
    with pytest.raises(LairenError, match="already used"):
        registry.set_alias("kimi", "user-1--device-2", "shared")


def test_set_alias_can_rename_and_skip_itself(tmp_path) -> None:
    registry = make_registry(tmp_path)
    registry.set_alias("kimi", "user-1--device-1", "kimi-a")
    registry.set_alias("kimi", "user-1--device-1", "kimi-b")

    assert registry.resolve("kimi-b").id == "user-1--device-1"
    with pytest.raises(LairenError, match="unknown account"):
        registry.resolve("kimi-a")


def test_clear_alias(tmp_path) -> None:
    registry = make_registry(tmp_path)
    registry.set_alias("kimi", "user-1--device-1", "kimi-a")
    registry.clear_alias("kimi", "user-1--device-1")

    assert registry.get("kimi", "user-1--device-1").alias is None
    with pytest.raises(LairenError, match="unknown account"):
        registry.resolve("kimi-a")


def test_upsert_preserves_alias_on_reregistration(tmp_path) -> None:
    registry = make_registry(tmp_path)
    registry.set_alias("kimi", "user-1--device-1", "kimi-a")

    registry.upsert(Account("kimi", "user-1--device-1", "new-label", "/tmp/new"))

    updated = registry.get("kimi", "user-1--device-1")
    assert updated.alias == "kimi-a"
    assert updated.label == "new-label"


def test_alias_roundtrips_through_json(tmp_path) -> None:
    registry = make_registry(tmp_path)
    registry.set_alias("kimi", "user-1--device-1", "kimi-a")

    reloaded = Registry(tmp_path / "registry.json").resolve("kimi-a")
    assert reloaded.to_dict()["alias"] == "kimi-a"
