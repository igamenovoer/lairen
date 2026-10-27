"""Pull refreshed credentials from known homes back into the store."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lairen.deployments import DeploymentLog, record_event
from lairen.errors import LairenError
from lairen.models import Account
from lairen.paths import Paths
from lairen.providers.base import Identity, Provider
from lairen.store import CredentialStore, Registry

Freshness = tuple[float, float, float]


@dataclass(frozen=True)
class SyncCandidate:
    """A live credential copy found in a provider home."""

    home: Path
    blob: str
    identity: Identity
    refresh_expires_at: float
    access_expires_at: float
    mtime: float

    @property
    def freshness(self) -> Freshness:
        return (self.refresh_expires_at, self.access_expires_at, self.mtime)


@dataclass
class SyncPlan:
    """What sync would do for one account."""

    account: Account
    state: str = "current"
    home: Path | None = None
    blob: str | None = None
    old_access_expires_at: float | None = None
    new_access_expires_at: float | None = None
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass
class OverwriteCheck:
    """Whether deploying over an existing target would lose a newer credential."""

    blocked: bool = False
    reason: str | None = None
    advice: str | None = None
    warning: str | None = None


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _expiry_pair(adapter: Provider, blob: str) -> tuple[float, float]:
    try:
        usage = adapter.local_usage(blob)
    except LairenError:
        return 0.0, 0.0
    return (
        _number(usage.get("refresh_token_expires_at")),
        _number(usage.get("access_token_expires_at")),
    )


def _canonical(blob: str) -> str:
    """Return a formatting-insensitive representation of a JSON credential."""
    try:
        return json.dumps(json.loads(blob), sort_keys=True, separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        return blob.strip()


def is_fresher(adapter: Provider, candidate_blob: str, stored_blob: str) -> bool:
    """Return True when a candidate credential is newer than the stored one."""
    candidate_pair = _expiry_pair(adapter, candidate_blob)
    stored_pair = _expiry_pair(adapter, stored_blob)
    if candidate_pair != stored_pair:
        return candidate_pair > stored_pair
    return candidate_pair != (0.0, 0.0) and _canonical(candidate_blob) != _canonical(stored_blob)


def candidate_homes(
    paths: Paths,
    account: Account,
    *,
    extra_homes: tuple[Path, ...] = (),
    include_known: bool = True,
) -> list[Path]:
    """Return the homes that may hold a live copy of the account."""
    homes: list[Path] = []
    if include_known:
        log = DeploymentLog(paths.deployments_path)
        for entry in log.leases_for(log.related_refs(account.ref)):
            raw = str(entry.get("home") or "")
            if raw:
                homes.append(Path(raw).expanduser().resolve())
        if account.source_home:
            homes.append(Path(account.source_home).expanduser().resolve())
    homes.extend(home.expanduser().resolve() for home in extra_homes)

    seen: set[str] = set()
    result: list[Path] = []
    for home in homes:
        key = str(home)
        if key not in seen:
            seen.add(key)
            result.append(home)
    return result


def check_overwrite(
    registry: Registry,
    store: CredentialStore,
    adapter: Provider,
    target_home: Path,
    target_path: Path,
    deployed_ref: str,
) -> OverwriteCheck:
    """Inspect an existing target before deploy replaces it."""
    try:
        target_blob = target_path.read_text(encoding="utf-8")
        identity = adapter.parse_identity(target_home, target_blob)
    except (OSError, UnicodeDecodeError, LairenError):
        return OverwriteCheck()

    target_ref = f"{adapter.name}/{identity.id}"
    account = registry.get(adapter.name, identity.id)
    if account is None:
        return OverwriteCheck(
            warning=(
                f"target {target_path} holds an unregistered credential for "
                f"{target_ref}; it will be overwritten"
            )
        )

    stored_blob = store.get(adapter.name, identity.id)
    if stored_blob is None:
        return OverwriteCheck(
            blocked=True,
            reason=f"it holds a credential for {target_ref}, but the store has no copy",
            advice=f"Run `lairen update {target_ref} --home {target_home}` to save it first.",
        )

    if not is_fresher(adapter, target_blob, stored_blob):
        return OverwriteCheck()

    if target_ref == deployed_ref:
        advice = (
            f"Run `lairen sync {deployed_ref} --home {target_home}` or "
            f"`lairen deploy {deployed_ref} --home {target_home} --refresh` first."
        )
    else:
        advice = f"Run `lairen sync {target_ref} --home {target_home}` first."
    return OverwriteCheck(
        blocked=True,
        reason=f"it holds a newer credential for {target_ref} than the registry copy",
        advice=advice,
    )


def _read_candidate(adapter: Provider, home: Path) -> SyncCandidate:
    blob = adapter.read_live(home)
    identity = adapter.parse_identity(home, blob)
    refresh_expires, access_expires = _expiry_pair(adapter, blob)
    try:
        mtime = adapter.credential_path_for(home).stat().st_mtime
    except OSError:
        mtime = 0.0
    return SyncCandidate(
        home=home,
        blob=blob,
        identity=identity,
        refresh_expires_at=refresh_expires,
        access_expires_at=access_expires,
        mtime=mtime,
    )


def plan_sync(
    account: Account,
    stored_blob: str | None,
    adapter: Provider,
    homes: list[Path],
) -> SyncPlan:
    """Choose the freshest same-identity credential among the given homes."""
    plan = SyncPlan(account=account)
    if stored_blob is None:
        plan.state = "missing-store-blob"
        return plan
    if not homes:
        plan.state = "no-known-homes"
        return plan

    stored_refresh, stored_access = _expiry_pair(adapter, stored_blob)
    candidates: list[SyncCandidate] = []
    for home in homes:
        try:
            candidate = _read_candidate(adapter, home)
        except (OSError, LairenError) as exc:
            plan.problems.append(f"cannot read {home}: {exc}")
            continue
        if candidate.identity.id != account.id:
            plan.problems.append(
                f"{home} now belongs to {adapter.name}/{candidate.identity.id}; "
                f"run lairen update {account.ref} --home {home}"
            )
            continue
        candidates.append(candidate)

    if not candidates:
        return plan

    best = max(candidates, key=lambda item: item.freshness)
    stored_pair = (stored_refresh, stored_access)
    candidate_pair = (best.refresh_expires_at, best.access_expires_at)
    if is_fresher(adapter, best.blob, stored_blob):
        plan.state = "update"
        plan.home = best.home
        plan.blob = best.blob
        plan.old_access_expires_at = stored_access or None
        plan.new_access_expires_at = best.access_expires_at or None
    elif stored_pair == (0.0, 0.0) and candidate_pair == (0.0, 0.0):
        plan.notes.append("no token expiry metadata; use lairen update to force a refresh")
    return plan


def apply_sync(paths: Paths, store: CredentialStore, plan: SyncPlan) -> None:
    """Write a planned update into the store and record the event."""
    if plan.state != "update" or plan.blob is None or plan.home is None:
        return
    store.set(plan.account.provider, plan.account.id, plan.blob)
    record_event(
        paths.deployments_path,
        "sync",
        plan.account,
        home=str(plan.home),
        source_home=plan.account.source_home,
    )
