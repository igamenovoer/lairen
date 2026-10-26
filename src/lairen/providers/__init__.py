"""Provider registry."""

from __future__ import annotations

from ..errors import LairenError
from .base import Identity, Provider
from .codex import CodexProvider
from .kimi import KimiProvider

_IMPLEMENTATIONS = (CodexProvider(), KimiProvider())
PROVIDERS: dict[str, Provider] = {
    provider.name: provider for provider in _IMPLEMENTATIONS
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(PROVIDERS))
        raise LairenError(f"unknown provider {name!r}; choose one of: {choices}") from exc


__all__ = ["Identity", "PROVIDERS", "Provider", "get_provider"]
