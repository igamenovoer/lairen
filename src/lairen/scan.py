"""Discover Codex and Kimi credential homes under a directory tree.

The patterns mirror the upstream clients:

- Codex: ``CODEX_HOME`` (default ``~/.codex``) containing ``auth.json``.
- Kimi Code: ``KIMI_CODE_HOME`` (default ``~/.kimi-code``) containing
  ``credentials/<name>.json`` (``kimi-code.json`` or ``kimi-code-env-*.json``).

A project may also keep a local ``.codex`` or ``.kimi-code`` directory.  Both
shapes are detected and validated by parsing the credential JSON, not by name
alone.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from lairen.errors import LairenError
from lairen.providers import PROVIDERS
from lairen.providers.base import Identity

IGNORED_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pixi",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "target",
    "venv",
}

CODEX_PATTERNS = ("auth.json",)
KIMI_CREDENTIAL_DIRS = ("credentials",)
SCAN_PROVIDERS = ("codex", "kimi")


@dataclass(frozen=True)
class ScanHit:
    provider: str
    home: Path
    credential: Path
    depth: int
    mtime: float
    identity: Identity

    @property
    def ref(self) -> str:
        return f"{self.provider}/{self.identity.id}"


def _iter_dirs(root: Path, max_depth: int) -> Iterator[tuple[Path, int]]:
    yield root, 0
    if max_depth <= 0:
        return
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, level = stack.pop()
        if level >= max_depth:
            continue
        try:
            children = sorted(
                (
                    child
                    for child in current.iterdir()
                    if child.is_dir() and not child.is_symlink()
                ),
                key=lambda child: child.name,
                reverse=True,
            )
        except OSError:
            continue
        for child in children:
            if child.name in IGNORED_DIRS:
                continue
            child_level = level + 1
            yield child, child_level
            stack.append((child, child_level))


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _looks_like_codex(data: dict[str, object]) -> bool:
    return (
        isinstance(data.get("tokens"), dict)
        or "OPENAI_API_KEY" in data
        or "auth_mode" in data
    )


def _looks_like_kimi(data: dict[str, object]) -> bool:
    has_token = "access_token" in data or "refresh_token" in data
    has_shape = "scope" in data or "expires_at" in data or "token_type" in data
    return has_token and has_shape


def _codex_candidates(directory: Path) -> Iterable[Path]:
    yield directory / "auth.json"
    yield directory / ".codex" / "auth.json"


def _kimi_candidates(directory: Path) -> Iterable[Path]:
    homes = [directory / ".kimi-code", directory / ".kimi"]
    if (directory / "credentials").is_dir():
        homes.append(directory)
    for home in homes:
        credentials = home / "credentials"
        if not credentials.is_dir():
            continue
        yield from sorted(credentials.glob("*.json"))


def _hit(provider: str, credential: Path, depth: int) -> ScanHit | None:
    data = _read_json(credential)
    if data is None:
        return None
    adapter = PROVIDERS[provider]
    if provider == "codex" and not _looks_like_codex(data):
        return None
    if provider == "kimi" and not _looks_like_kimi(data):
        return None
    try:
        blob = credential.read_text(encoding="utf-8")
        identity = adapter.parse_identity(credential.parent, blob)
        mtime = credential.stat().st_mtime
    except (OSError, UnicodeDecodeError, LairenError):
        return None
    home = credential.parent if provider == "codex" else credential.parent.parent
    return ScanHit(
        provider=provider,
        home=home,
        credential=credential,
        depth=depth,
        mtime=mtime,
        identity=identity,
    )


def scan_accounts(
    root: Path,
    depth: int = 1,
    providers: Iterable[str] = SCAN_PROVIDERS,
) -> list[ScanHit]:
    """Return every matching credential under ``root`` up to ``depth`` levels.

    Depth 0 inspects only ``root`` itself; depth 1 also inspects its immediate
    child directories (the default "top level").
    """
    if depth < 0:
        raise LairenError("scan depth must be zero or greater")
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise LairenError(f"scan root is not a directory: {root}")

    selected = tuple(providers)
    unknown = [name for name in selected if name not in SCAN_PROVIDERS]
    if unknown:
        raise LairenError(f"scan supports only {', '.join(SCAN_PROVIDERS)}; got {unknown}")

    hits: dict[tuple[str, Path], ScanHit] = {}
    for directory, level in _iter_dirs(root, depth):
        if "codex" in selected:
            for credential in _codex_candidates(directory):
                hit = _hit("codex", credential, level)
                if hit is not None:
                    hits[("codex", credential.resolve())] = hit
        if "kimi" in selected:
            for credential in _kimi_candidates(directory):
                hit = _hit("kimi", credential, level)
                if hit is not None:
                    hits[("kimi", credential.resolve())] = hit

    return sorted(hits.values(), key=lambda item: (item.provider, item.identity.id, str(item.home)))


def _fresh_mtime(hit: ScanHit) -> float:
    try:
        return hit.credential.stat().st_mtime
    except OSError:
        return hit.mtime


def best_per_account(hits: Iterable[ScanHit]) -> list[ScanHit]:
    """Collapse duplicate copies of one account, keeping the newest file."""
    best: dict[tuple[str, str], ScanHit] = {}
    for hit in hits:
        key = (hit.provider, hit.identity.id)
        current = best.get(key)
        if current is None or _fresh_mtime(hit) > _fresh_mtime(current):
            best[key] = hit
    return sorted(best.values(), key=lambda item: (item.provider, item.identity.id))
