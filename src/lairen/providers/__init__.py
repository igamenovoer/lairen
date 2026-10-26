"""Provider registry and capability metadata."""

from __future__ import annotations

from lairen.errors import LairenError
from lairen.providers.base import Identity, Provider
from lairen.providers.claude import ClaudeProvider
from lairen.providers.codex import CodexProvider
from lairen.providers.commandcode import CommandCodeProvider
from lairen.providers.cursor import CursorProvider
from lairen.providers.kimi import KimiProvider
from lairen.providers.opencode import OpenCodeProvider

_IMPLEMENTATIONS = (
    ClaudeProvider(),
    CodexProvider(),
    CommandCodeProvider(),
    CursorProvider(),
    KimiProvider(),
    OpenCodeProvider(),
)
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
