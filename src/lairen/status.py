"""Project credential inspection for ``lairen status``."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from lairen.deployments import DeploymentLog
from lairen.errors import LairenError
from lairen.holder import HOLDER_PROBLEM_STATES, holder_state
from lairen.models import Account
from lairen.paths import Paths
from lairen.providers import get_provider
from lairen.providers.base import Provider
from lairen.store import CredentialStore, Registry
from lairen.util import epoch_to_iso

STATUS_PROVIDERS = ("codex", "kimi")
PROJECT_HOMES = {"codex": ".codex", "kimi": ".kimi-code"}
AUTH_PROBLEM_STATES = frozenset(
    {"invalid", "unregistered", "drifted", "missing-auth"}
)


@dataclass(frozen=True)
class Problem:
    kind: str
    ref: str | None
    message: str
    fix: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass
class Lease:
    project: str | None
    home: str
    deployed_at: str | None
    live: bool | None = None
    mode: str = "copy"

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "home": self.home,
            "deployed_at": self.deployed_at,
            "live": self.live,
            "mode": self.mode,
        }


@dataclass
class ShellBinding:
    """A holder home activated through the current process environment."""

    provider: str
    env_var: str
    home: str
    ref: str
    alias: str | None
    holder_state: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "env_var": self.env_var,
            "home": self.home,
            "ref": self.ref,
            "alias": self.alias,
            "holder_state": self.holder_state,
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
    source: str = "copy"
    expires_at: str | None = None
    expires_in_seconds: int | None = None
    registry_expires_at: str | None = None
    registry_expires_in_seconds: int | None = None
    leases: list[Lease] = field(default_factory=list)
    holder: str | None = None
    holder_state: str = "none"
    holder_reason: str | None = None
    link: str | None = None
    link_mismatch: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "ref": self.ref,
            "alias": self.alias,
            "label": self.label,
            "home": str(self.home),
            "credential": str(self.credential) if self.credential else None,
            "source": self.source,
            "state": self.state,
            "expires_at": self.expires_at,
            "expires_in_seconds": self.expires_in_seconds,
            "registry_expires_at": self.registry_expires_at,
            "registry_expires_in_seconds": self.registry_expires_in_seconds,
            "leases": [lease.to_dict() for lease in self.leases],
            "holder": self.holder,
            "holder_state": self.holder_state,
            "holder_reason": self.holder_reason,
            "link": self.link,
            "link_mismatch": self.link_mismatch,
            "error": self.error,
        }


@dataclass
class ProjectReport:
    project: Path
    accounts: list[AccountStatus] = field(default_factory=list)
    shell: list[ShellBinding] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def warnings(self) -> list[str]:
        return [problem.message for problem in self.problems]

    def to_dict(self) -> dict[str, object]:
        return {
            "project": str(self.project),
            "ok": self.ok,
            "accounts": [item.to_dict() for item in self.accounts],
            "shell": [binding.to_dict() for binding in self.shell],
            "problems": [problem.to_dict() for problem in self.problems],
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ProjectHome:
    """A project-scope home path and the real home it resolves to."""

    path: Path
    home: Path
    link: str | None = None


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
    accounts = registry.list()
    by_ref = {account.ref: account for account in accounts}
    by_home = {
        (account.provider, Path(account.holder.home).expanduser().resolve()): account
        for account in accounts
        if account.holder is not None and account.holder.home
    }
    report = ProjectReport(project=project)

    for provider in selected:
        for home in _project_homes(project, provider):
            report.accounts.extend(
                _inspect_home(provider, home, by_ref, by_home, store, log)
            )
        binding = _shell_binding(provider, by_home)
        if binding is not None:
            report.shell.append(binding)

    report.problems = _problems(report.accounts, report.shell, by_ref)
    return report


def format_problems(problems: list[Problem]) -> str:
    lines = [f"strict status failed: {len(problems)} problem(s)"]
    for problem in problems:
        lines.append(f"  {problem.message}")
        if problem.fix:
            lines.append(f"    fix: {problem.fix}")
    return "\n".join(lines)


def _shell_binding(
    provider: str,
    by_home: dict[tuple[str, Path], Account],
) -> ShellBinding | None:
    adapter = get_provider(provider)
    if not adapter.env_var:
        return None
    raw_home = os.environ.get(adapter.env_var)
    if not raw_home:
        return None
    home = Path(raw_home).expanduser().resolve()
    account = by_home.get((provider, home))
    if account is None:
        return None
    return ShellBinding(
        provider=provider,
        env_var=adapter.env_var,
        home=str(home),
        ref=account.ref,
        alias=account.alias,
        holder_state=holder_state(provider, account.holder),
    )


def _project_homes(project: Path, provider: str) -> list[ProjectHome]:
    name = PROJECT_HOMES[provider]
    candidates: list[Path] = []
    local = project / name
    if local.is_dir() or local.is_symlink():
        candidates.append(local)
    if project.name == name and (project.is_dir() or project.is_symlink()):
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
    homes: list[ProjectHome] = []
    for candidate in candidates:
        entry = _project_home(candidate)
        if entry.home not in seen:
            seen.add(entry.home)
            homes.append(entry)
    return homes


def _project_home(path: Path) -> ProjectHome:
    if path.is_symlink():
        return ProjectHome(
            path=path,
            home=Path(os.path.realpath(path)),
            link=str(path),
        )
    return ProjectHome(path=path, home=path.resolve())


def _inspect_home(
    provider: str,
    entry: ProjectHome,
    by_ref: dict[str, Account],
    by_home: dict[tuple[str, Path], Account],
    store: CredentialStore,
    log: DeploymentLog,
) -> list[AccountStatus]:
    adapter = get_provider(provider)
    home = entry.home
    account = by_home.get((provider, home))
    if provider == "codex":
        credential = home / adapter.CREDENTIAL_RELPATH
        if not credential.is_file():
            return [_no_login(provider, entry, credential, account)]
        return [
            _inspect_credential(provider, entry, credential, by_ref, store, log)
        ]

    credentials_dir = home / "credentials"
    files = sorted(credentials_dir.glob("*.json")) if credentials_dir.is_dir() else []
    if not files:
        return [
            _no_login(
                provider,
                entry,
                home / adapter.CREDENTIAL_RELPATH,
                account,
            )
        ]
    return [
        _inspect_credential(provider, entry, credential, by_ref, store, log)
        for credential in files
    ]


def _no_login(
    provider: str,
    entry: ProjectHome,
    credential: Path,
    account: Account | None,
) -> AccountStatus:
    return AccountStatus(
        provider=provider,
        state="no-login",
        home=entry.home,
        credential=credential,
        ref=account.ref if account is not None else None,
        alias=account.alias if account is not None else None,
        label=account.label if account is not None else None,
        source="link" if entry.link else "copy",
        holder=account.holder.home if account and account.holder else None,
        holder_state=holder_state(provider, account.holder) if account else "none",
        holder_reason=_holder_reason(account),
        link=entry.link,
        link_mismatch=False,
    )


def _invalid(
    provider: str,
    entry: ProjectHome,
    credential: Path,
    account: Account | None,
    error: str,
) -> AccountStatus:
    return AccountStatus(
        provider=provider,
        state="invalid",
        home=entry.home,
        credential=credential,
        ref=account.ref if account is not None else None,
        alias=account.alias if account is not None else None,
        label=account.label if account is not None else None,
        source="link" if entry.link else "copy",
        holder=account.holder.home if account and account.holder else None,
        holder_state=holder_state(provider, account.holder) if account else "none",
        holder_reason=_holder_reason(account),
        link=entry.link,
        error=error,
    )


def _inspect_credential(
    provider: str,
    entry: ProjectHome,
    credential: Path,
    by_ref: dict[str, Account],
    store: CredentialStore,
    log: DeploymentLog,
) -> AccountStatus:
    adapter = get_provider(provider)
    home = entry.home
    try:
        blob = credential.read_text(encoding="utf-8")
        identity = adapter.parse_identity(home, blob)
    except (OSError, UnicodeDecodeError) as exc:
        account = None
        return _invalid(provider, entry, credential, account, str(exc))
    except LairenError as exc:
        account = None
        return _invalid(provider, entry, credential, account, str(exc))

    ref = f"{provider}/{identity.id}"
    account = by_ref.get(ref)
    stored_blob = store.get(provider, identity.id)
    project_expires, project_remaining = _expiry(adapter, blob)
    registry_expires, registry_remaining = (
        _expiry(adapter, stored_blob) if stored_blob is not None else (None, None)
    )
    source = "link" if entry.link else "copy"

    if account is None:
        state = "unregistered"
    elif stored_blob is None:
        state = "current" if source == "link" else "missing-auth"
    elif stored_blob.strip() == blob.strip():
        state = "current"
    else:
        state = "drifted"

    holder = account.holder if account is not None else None
    link_mismatch = False
    if entry.link is not None and holder is not None and holder.home:
        link_target = Path(os.path.realpath(entry.link))
        holder_home = Path(holder.home).expanduser().resolve()
        link_mismatch = link_target != holder_home

    leases = _leases(log, ref, home, provider, identity.id, entry.link)

    return AccountStatus(
        provider=provider,
        state=state,
        home=home,
        credential=credential,
        ref=ref,
        alias=account.alias if account is not None else None,
        label=account.label if account is not None else identity.label,
        source=source,
        expires_at=project_expires,
        expires_in_seconds=project_remaining,
        registry_expires_at=registry_expires,
        registry_expires_in_seconds=registry_remaining,
        leases=leases,
        holder=holder.home if holder is not None else None,
        holder_state=holder_state(provider, holder) if account is not None else "none",
        holder_reason=_holder_reason(account),
        link=entry.link,
        link_mismatch=link_mismatch,
    )


def _holder_reason(account: Account | None) -> str | None:
    if account is None or account.holder is None or not account.holder.stale_since:
        return None
    reason = account.holder.stale_reason or "credential copy may have rotated"
    return f"since {account.holder.stale_since}: {reason}"


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
    link_path: str | None = None,
) -> list[Lease]:
    leases: list[Lease] = []
    for entry in log.leases_for(log.related_refs(ref)):
        raw_home = str(entry.get("home") or "")
        if not raw_home:
            continue
        mode = str(entry.get("mode") or ("link" if entry.get("action") == "link" else "copy"))
        if mode == "link":
            display_home = str(Path(raw_home).expanduser())
            live_path = Path(raw_home).expanduser().resolve()
            if link_path is not None and display_home == str(Path(link_path).expanduser()):
                continue
        else:
            live_path = Path(raw_home).expanduser().resolve()
            display_home = str(live_path)
            if live_path == home:
                continue
            if link_path is not None and live_path == Path(link_path).expanduser().resolve():
                continue
        project = entry.get("project")
        leases.append(
            Lease(
                project=str(project) if project else None,
                home=display_home,
                deployed_at=str(entry.get("ts") or "") or None,
                live=_lease_is_live(provider, live_path, account_id),
                mode=mode,
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


def _problems(
    accounts: list[AccountStatus],
    shell: list[ShellBinding],
    by_ref: dict[str, Account],
) -> list[Problem]:
    problems: list[Problem] = []
    seen: set[tuple[str, str | None]] = set()

    def add(kind: str, ref: str | None, message: str, fix: str | None = None) -> None:
        key = (kind, ref)
        if key in seen:
            return
        seen.add(key)
        problems.append(Problem(kind=kind, ref=ref, message=message, fix=fix))

    for item in accounts:
        if item.state == "invalid":
            add(
                "invalid",
                item.ref,
                f"invalid credential at {item.credential}: {item.error}",
                f"lairen account update {item.ref} --home {item.home}" if item.ref else None,
            )
        elif item.state == "unregistered":
            add(
                "unregistered",
                item.ref,
                f"unregistered account {item.ref} at {item.home}",
                f"lairen account add --provider {item.provider} --home {item.home}",
            )
        elif item.state == "drifted" and item.source != "link":
            add(
                "drifted",
                item.ref,
                f"{item.ref} differs from the stored auth",
                f"lairen account sync {item.ref} --home {item.holder or item.home}",
            )
        elif item.state == "missing-auth":
            add(
                "missing-auth",
                item.ref,
                f"{item.ref} has no stored auth for copy source {item.home}",
                f"lairen account sync {item.ref} --home {item.holder or item.home}",
            )

        account = by_ref.get(item.ref) if item.ref else None
        if account is not None and account.holder is not None:
            _holder_problem(add, account, item.holder_state, item.holder_reason)

        if item.link_mismatch and item.ref and item.link:
            add(
                "link-mismatch",
                item.ref,
                f"{item.ref}: {item.link} does not point at holder {item.holder}",
                f"lairen deploy link {item.ref} --force",
            )

    for binding in shell:
        account = by_ref.get(binding.ref)
        if account is not None:
            _holder_problem(add, account, binding.holder_state, _holder_reason(account))

    return problems


def _holder_problem(add, account: Account, state: str, reason: str | None) -> None:
    if state not in HOLDER_PROBLEM_STATES or account.holder is None:
        return
    home = account.holder.home
    if state == "possibly-stale":
        message = f"{account.ref}: holder {home} is possibly stale"
        if reason:
            message = f"{message} ({reason})"
        add(
            "holder-possibly-stale",
            account.ref,
            message,
            f"lairen account sync {account.ref} --home {home}",
        )
    elif state == "missing":
        add(
            "holder-missing",
            account.ref,
            f"{account.ref}: holder {home} is missing",
            f"lairen account set-home {account.ref} --home PATH",
        )
    elif state == "no-login":
        add(
            "holder-no-login",
            account.ref,
            f"{account.ref}: holder {home} has no login",
            f"lairen account sync {account.ref} --home {home}",
        )
