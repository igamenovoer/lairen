"""Account/project associations derived from the deployment ledger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lairen.deployments import DeploymentLog
from lairen.models import Account


@dataclass(frozen=True)
class Association:
    """One account deployed into one home, with its ledger state."""

    provider: str
    ref: str
    alias: str | None
    label: str
    project: str | None
    home: str
    deployed_at: str | None
    state: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "ref": self.ref,
            "alias": self.alias,
            "label": self.label,
            "project": self.project,
            "home": self.home,
            "deployed_at": self.deployed_at,
            "state": self.state,
        }


@dataclass(frozen=True)
class AvailableAccount:
    """A registered account with no active deployment."""

    account: Account
    last_assignment: Association | None

    def to_dict(self) -> dict[str, object]:
        return {
            "ref": self.account.ref,
            "provider": self.account.provider,
            "alias": self.account.alias,
            "label": self.account.label,
            "last_assignment": (
                self.last_assignment.to_dict() if self.last_assignment else None
            ),
        }


def build_associations(
    accounts: list[Account],
    log: DeploymentLog,
) -> list[Association]:
    """Build the account/project graph from deploy entries.

    The newest deploy for a ``(provider, home)`` pair is active. Every older
    deploy to the same pair is overwritten, even when it belongs to another
    account. An identity-changing update overwrites earlier deploys.
    """
    entries = log.entries()
    deploys: list[tuple[int, dict[str, object], str, str]] = []
    for index, entry in enumerate(entries):
        if entry.get("action") != "deploy":
            continue
        ref = str(entry.get("ref") or "")
        raw_home = str(entry.get("home") or "")
        if not ref or not raw_home:
            continue
        provider = str(entry.get("provider") or ref.partition("/")[0])
        home = str(Path(raw_home).expanduser().resolve())
        deploys.append((index, entry, provider, home))

    updates: list[tuple[str, int, str, str]] = []
    for index, entry in enumerate(entries):
        if entry.get("action") != "update":
            continue
        current = str(entry.get("ref") or "")
        previous = str(entry.get("previous_ref") or "")
        if current and previous and current != previous:
            updates.append((str(entry.get("ts") or ""), index, current, previous))

    latest: dict[tuple[str, str], tuple[str, int]] = {}
    for index, entry, provider, home in deploys:
        key = (provider, home)
        latest_stamp = (str(entry.get("ts") or ""), index)
        if key not in latest or latest_stamp >= latest[key]:
            latest[key] = latest_stamp

    associations: list[Association] = []
    for account in accounts:
        related = log.related_refs(account.ref)
        rebind_stamp: tuple[str, int] | None = None
        for update_stamp, update_index, current_ref, previous_ref in updates:
            if current_ref in related and previous_ref in related:
                candidate = (update_stamp, update_index)
                if rebind_stamp is None or candidate > rebind_stamp:
                    rebind_stamp = candidate
        per_home: dict[str, tuple[str, int, dict[str, object]]] = {}
        for index, entry, provider, home in deploys:
            if provider != account.provider:
                continue
            if str(entry.get("ref") or "") not in related:
                continue
            deploy_stamp = (str(entry.get("ts") or ""), index)
            current_entry = per_home.get(home)
            if current_entry is None or deploy_stamp >= (
                current_entry[0],
                current_entry[1],
            ):
                per_home[home] = (deploy_stamp[0], index, entry)

        for home, (deployed_at, index, entry) in per_home.items():
            key = (account.provider, home)
            newest = latest.get(key)
            if newest is None:
                state = "active"
            else:
                state = (
                    "active"
                    if (deployed_at, index) >= newest
                    else "overwritten"
                )
            if rebind_stamp is not None and (deployed_at, index) < rebind_stamp:
                state = "overwritten"
            project = entry.get("project")
            associations.append(
                Association(
                    provider=account.provider,
                    ref=account.ref,
                    alias=account.alias,
                    label=account.label,
                    project=str(project) if project else None,
                    home=home,
                    deployed_at=deployed_at or None,
                    state=state,
                )
            )

    return sorted(
        associations,
        key=lambda item: (
            item.provider,
            item.ref,
            item.project or "",
            item.deployed_at or "",
            item.home,
        ),
    )


def available_accounts(
    accounts: list[Account],
    associations: list[Association],
) -> list[AvailableAccount]:
    """Return accounts without any active association.

    Overwritten assignments do not count as assigned. The newest inactive
    association is kept so the caller can explain why.
    """
    by_ref: dict[str, list[Association]] = {}
    for association in associations:
        by_ref.setdefault(association.ref, []).append(association)

    assigned = {
        association.ref
        for association in associations
        if association.state == "active"
    }
    result: list[AvailableAccount] = []
    for account in accounts:
        if account.ref in assigned:
            continue
        edges = by_ref.get(account.ref, [])
        last = max(
            edges,
            key=lambda item: (item.deployed_at or "", item.home),
            default=None,
        )
        result.append(AvailableAccount(account=account, last_assignment=last))
    return sorted(result, key=lambda item: (item.account.provider, item.account.id))
