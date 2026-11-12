"""Derived holder health and stale-mark helpers."""

from __future__ import annotations

from pathlib import Path

from lairen.models import Holder
from lairen.providers import get_provider
from lairen.util import utc_now

HOLDER_STATES = ("none", "ok", "possibly-stale", "missing", "no-login")
HOLDER_PROBLEM_STATES = frozenset({"possibly-stale", "missing", "no-login"})


def holder_state(provider_name: str, holder: Holder | None) -> str:
    """Return the live state of an account holder home."""
    if holder is None or not holder.home:
        return "none"
    home = Path(holder.home).expanduser()
    if not home.is_dir():
        return "missing"
    adapter = get_provider(provider_name)
    if not adapter.credential_path_for(home).is_file():
        return "no-login"
    if holder.stale_since:
        return "possibly-stale"
    return "ok"


def mark_holder_stale(holder: Holder, reason: str, *, when: str | None = None) -> None:
    holder.stale_since = when or utc_now()
    holder.stale_reason = reason


def clear_holder_stale(holder: Holder) -> None:
    holder.stale_since = None
    holder.stale_reason = None
