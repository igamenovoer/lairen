"""Project credential inspection for ``lairen status``."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from lairen.deployments import DeploymentLog, project_root_for_home
from lairen.errors import LairenError
from lairen.paths import Paths
from lairen.providers import get_provider
from lairen.providers.base import Provider
from lairen.store import CredentialStore, Registry
from lairen.util import epoch_to_iso

STATUS_PROVIDERS = ("codex", "kimi")
PROJECT_HOMES = {"codex": ".codex", "kimi": ".kimi-code"}
PROBLEM_STATES = frozenset(
    {"invalid", "unregistered", "drifted", "missing-store-blob"}
)


@dataclass
class Lease:
    project: str | None
    home: str
    deployed_at: str | None
    legacy: bool = False
    live: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "home": self.home,
            "deployed_at": self.deployed_at,
            "legacy": self.legacy,
            "live": self.live,
        }


@dataclass
class AccountStatus:
    provider: str
    state: str
    home: Path
    credential: Path | None = None
    ref: str | None = None
    alias: str | None = None
    label: str | None = None
    expires_at: str | None = None
    expires_in_seconds: int | None = None
    registry_expires_at: str | None = None
    registry_expires_in_seconds: int | None = None
    leases: list[Lease] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "ref": self.ref,
            "alias": self.alias,
            "label": self.label,
            "home": str(self.home),
            "credential": str(self.credential) if self.credential else None,
            "state": self.state,
            "expires_at": self.expires_at,
            "expires_in_seconds": self.expires_in_seconds,
            "registry_expires_at": self.registry_expires_at,
            "registry_expires_in_seconds": self.registry_expires_in_seconds,
            "leases": [lease.to_dict() for lease in self.leases],
            "error": self.error,
        }


@dataclass
class ProjectReport:
    project: Path
    accounts: list[AccountStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[AccountStatus]:
        return [item for item in self.accounts if item.state in PROBLEM_STATES]

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, object]:
        return {
            "project": str(self.project),
            "ok": self.ok,
            "accounts": [item.to_dict() for item in self.accounts],
            "warnings": self.warnings,
        }


def inspect_project(
    directory: str | Path,
    providers: Iterable[str],
    paths: Paths,
) -> ProjectReport:
    project = Path(directory).expanduser().resolve()
    if not project.is_dir():
        raise LairenError(f"project directory not found: {project}")

    selected = tuple(providers)
    unknown = [name for name in selected if name not in STATUS_PROVIDERS]
    if unknown:
        raise LairenError(
            f"status supports only {', '.join(STATUS_PROVIDERS)}; got {unknown}"
        )

    registry = Registry(paths.registry_path)
    store = CredentialStore(paths.credentials_path)
    log = DeploymentLog(paths.deployments_path)
    report = ProjectReport(project=project)

    for provider in selected:
        for home in _project_homes(project, provider):
            report.accounts.extend(_inspect_home(provider, home, registry, store, log))

    report.warnings = _warnings(report.accounts)
    return report


def _project_homes(project: Path, provider: str) -> list[Path]:
    name = PROJECT_HOMES[provider]
    candidates: list[Path] = []
    local = project / name
    if local.is_dir():
        candidates.append(local)
    if project.name == name and project.is_dir():
        candidates.append(project)

    # A directory can also be a provider home itself: CODEX_HOME with auth.json
    # at its root, or KIMI_CODE_HOME with credentials/*.json at its root.
    if provider == "codex" and (project / "auth.json").is_file():
        candidates.append(project)
    if provider == "kimi":
        credentials = project / "credentials"
        if credentials.is_dir() and any(credentials.glob("*.json")):
            candidates.append(project)

    seen: set[Path] = set()
    homes: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            homes.append(resolved)
    return homes


def _inspect_home(
    provider: str,
    home: Path,
    registry: Registry,
    store: CredentialStore,
    log: DeploymentLog,
) -> list[AccountStatus]:
    adapter = get_provider(provider)
    if provider == "codex":
        credential = home / adapter.CREDENTIAL_RELPATH
        if not credential.is_file():
            return [_no_login(provider, home, credential)]
        return [_inspect_credential(provider, home, credential, registry, store, log)]

    credentials_dir = home / "credentials"
    files = sorted(credentials_dir.glob("*.json")) if credentials_dir.is_dir() else []
    if not files:
        return [
            _no_login(
                provider,
                home,
                home / adapter.CREDENTIAL_RELPATH,
            )
        ]
    return [
        _inspect_credential(provider, home, credential, registry, store, log)
        for credential in files
    ]


def _no_login(provider: str, home: Path, credential: Path) -> AccountStatus:
    return AccountStatus(
        provider=provider,
        state="no-login",
        home=home,
        credential=credential,
    )


def _invalid(
    provider: str,
    home: Path,
    credential: Path,
    error: str,
) -> AccountStatus:
    return AccountStatus(
        provider=provider,
        state="invalid",
        home=home,
        credential=credential,
        error=error,
    )


def _inspect_credential(
    provider: str,
    home: Path,
    credential: Path,
    registry: Registry,
    store: CredentialStore,
    log: DeploymentLog,
) -> AccountStatus:
    adapter = get_provider(provider)
    try:
        blob = credential.read_text(encoding="utf-8")
        identity = adapter.parse_identity(home, blob)
    except (OSError, UnicodeDecodeError) as exc:
        return _invalid(provider, home, credential, str(exc))
    except LairenError as exc:
        return _invalid(provider, home, credential, str(exc))

    ref = f"{provider}/{identity.id}"
    account = registry.get(provider, identity.id)
    stored_blob = store.get(provider, identity.id)
    project_expires, project_remaining = _expiry(adapter, blob)
    registry_expires, registry_remaining = (
        _expiry(adapter, stored_blob) if stored_blob is not None else (None, None)
    )

    if account is None:
        state = "unregistered"
    elif stored_blob is None:
        state = "missing-store-blob"
    elif stored_blob == blob:
        state = "current"
    else:
        state = "drifted"

    leases = _leases(log, ref, home, provider, identity.id)
    if not leases and account is not None and account.last_deployed_home:
        legacy_home = str(
            Path(account.last_deployed_home).expanduser().resolve()
        )
        if legacy_home != str(home):
            leases.append(
                Lease(
                    project=project_root_for_home(legacy_home),
                    home=legacy_home,
                    deployed_at=account.last_deployed_at,
                    legacy=True,
                    live=_lease_is_live(provider, Path(legacy_home), identity.id),
                )
            )

    return AccountStatus(
        provider=provider,
        state=state,
        home=home,
        credential=credential,
        ref=ref,
        alias=account.alias if account is not None else None,
        label=account.label if account is not None else identity.label,
        expires_at=project_expires,
        expires_in_seconds=project_remaining,
        registry_expires_at=registry_expires,
        registry_expires_in_seconds=registry_remaining,
        leases=leases,
    )


def _expiry(adapter: Provider, blob: str) -> tuple[str | None, int | None]:
    try:
        usage = adapter.local_usage(blob)
    except LairenError:
        return None, None
    value = usage.get("access_token_expires_at")
    if not isinstance(value, (int, float)):
        return None, None
    return epoch_to_iso(value), int(float(value) - time.time())


def _leases(
    log: DeploymentLog,
    ref: str,
    home: Path,
    provider: str,
    account_id: str,
) -> list[Lease]:
    leases: list[Lease] = []
    for entry in log.leases_for(log.related_refs(ref)):
        raw_home = str(entry.get("home") or "")
        if not raw_home:
            continue
        lease_home = str(Path(raw_home).expanduser().resolve())
        if lease_home == str(home):
            continue
        project = entry.get("project") or project_root_for_home(lease_home)
        lease_path = Path(lease_home)
        leases.append(
            Lease(
                project=str(project) if project else None,
                home=lease_home,
                deployed_at=str(entry.get("ts") or "") or None,
                live=_lease_is_live(provider, lease_path, account_id),
            )
        )
    return leases


def _lease_is_live(provider: str, home: Path, account_id: str) -> bool:
    adapter = get_provider(provider)
    try:
        blob = adapter.read_live(home)
        identity = adapter.parse_identity(home, blob)
    except (OSError, UnicodeDecodeError, LairenError):
        return False
    return identity.id == account_id


def _warnings(accounts: list[AccountStatus]) -> list[str]:
    warnings: list[str] = []
    for item in accounts:
        if item.state == "invalid":
            warnings.append(f"invalid credential at {item.credential}: {item.error}")
        elif item.state == "unregistered":
            warnings.append(f"unregistered account {item.ref} at {item.home}")
        elif item.state == "drifted":
            warnings.append(f"{item.ref} differs from the registry credential")
        elif item.state == "missing-store-blob":
            warnings.append(f"{item.ref} has no stored credential blob")
        elif item.state == "no-login":
            warnings.append(f"no login at {item.home}")
    return warnings
