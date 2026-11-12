"""Click command-line interface for lairen 2.x."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from lairen import __version__
from lairen import manual as manual_content
from lairen.associations import Association, build_associations
from lairen.deployments import DeploymentLog, record_event
from lairen.errors import LairenError
from lairen.holder import clear_holder_stale, holder_state, mark_holder_stale
from lairen.migrations import MigrationReport, migrate_state
from lairen.models import Account, Auth, Holder
from lairen.paths import Paths
from lairen.providers import PROVIDERS, get_provider
from lairen.scan import best_per_account, scan_accounts
from lairen.schema import require_current_schema, schema_status
from lairen.shells import SHELL_CHOICES, export_command, normalize_shell
from lairen.status import ProjectReport, format_problems, inspect_project
from lairen.store import CredentialStore, Registry
from lairen.sync import apply_sync, candidate_homes, check_overwrite, plan_sync
from lairen.targets import (
    foreign_home_warning,
    resolve_deploy_target,
    resolve_link_target,
)
from lairen.util import epoch_to_iso, format_remaining, utc_now


class LairenGroup(click.Group):
    """Turn domain errors into clean Click errors."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except LairenError as exc:
            raise click.ClickException(str(exc)) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc


def _context() -> tuple[Paths, Registry, CredentialStore]:
    paths = Paths.resolve().ensure()
    require_current_schema(paths)
    return paths, Registry(paths.registry_path), CredentialStore(paths.credentials_path)


def _display_width(value: Any) -> int:
    return len(click.unstyle(str(value)))


def _pad_cell(value: Any, width: int) -> str:
    text = str(value)
    return text + " " * (width - _display_width(text))


def _print_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], _display_width(cell))
    click.echo(
        "  ".join(header.ljust(width) for header, width in zip(headers, widths, strict=True))
    )
    click.echo("  ".join("-" * width for width in widths))
    for row in rows:
        click.echo(
            "  ".join(_pad_cell(cell, width) for cell, width in zip(row, widths, strict=True))
        )


def _warn_experimental(provider_name: str) -> None:
    provider = get_provider(provider_name)
    if not provider.tested:
        click.echo(
            f"warning: the {provider.name} adapter is experimental "
            f"({provider.deploy_note or 'no live credentials in this project'})",
            err=True,
        )


def _label_tracks_identity(account: Account, old_id: str) -> bool:
    """Return True when the label was derived from the previous identity."""
    if account.label == old_id:
        return True
    return any(
        account.extra.get(key) is not None and str(account.extra[key]) == account.label
        for key in ("email", "user_id")
    )


def _style_alias(alias: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return alias
    return click.style(alias, fg="yellow", bold=True)


def _record_deployment(
    paths: Paths,
    action: str,
    account: Account,
    *,
    home: str | None = None,
    source_home: str | None = None,
    project: str | Path | None = None,
    previous_ref: str | None = None,
    mode: str | None = None,
) -> None:
    try:
        record_event(
            paths.deployments_path,
            action,
            account,
            home=home,
            source_home=source_home,
            project=project,
            previous_ref=previous_ref,
            mode=mode,
        )
    except OSError as exc:
        click.echo(f"warning: cannot write deployment log: {exc}", err=True)


def _auth_payload(
    account: Account,
    store: CredentialStore,
) -> dict[str, Any]:
    blob = store.get(account.provider, account.id)
    auth = account.auth
    return {
        "stored": bool(auth.stored) if auth is not None else False,
        "present": blob is not None,
        "captured_at": auth.captured_at if auth is not None else None,
        "source_home": auth.source_home if auth is not None else None,
    }


def _account_payload(
    account: Account,
    store: CredentialStore,
    associations: list[Association],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ref": account.ref,
        "provider": account.provider,
        "id": account.id,
        "label": account.label,
        "alias": account.alias,
        "created_at": account.created_at,
        "extra": account.extra,
        "auth": _auth_payload(account, store),
        "holder": account.holder.to_dict() if account.holder is not None else None,
        "holder_state": holder_state(account.provider, account.holder),
        "deployments": [item.to_dict() for item in associations],
    }
    return payload


def _associations_by_ref(
    accounts: list[Account],
    paths: Paths,
) -> dict[str, list[Association]]:
    items = build_associations(accounts, DeploymentLog(paths.deployments_path))
    result: dict[str, list[Association]] = {}
    for item in items:
        result.setdefault(item.ref, []).append(item)
    return result


def _active_deployments(items: list[Association]) -> list[Association]:
    return [item for item in items if item.state == "active"]


def _deployment_summary(items: list[Association]) -> str:
    active = _active_deployments(items)
    if not active:
        return "-"
    labels: list[str] = []
    for item in sorted(active, key=lambda entry: (entry.project or "", entry.home)):
        where = item.project or item.home
        labels.append(f"{where} ({item.mode})")
    return ", ".join(labels)


def _holder_cell(account: Account) -> str:
    return account.holder.home if account.holder is not None else "-"


def _auth_cell(account: Account, store: CredentialStore) -> str:
    blob = store.get(account.provider, account.id)
    if blob is not None:
        return "stored"
    if account.auth is not None and account.auth.stored:
        return "missing"
    return "none"


def _load_stored_blob(
    account: Account,
    store: CredentialStore,
) -> str:
    blob = store.get(account.provider, account.id)
    if blob is None:
        home = account.holder.home if account.holder is not None else "PATH"
        raise LairenError(
            f"{account.ref} has no stored auth; "
            f"run `lairen account sync {account.ref} --home {home}` first"
        )
    return blob


def _read_home_identity(adapter, home: Path):
    blob = adapter.read_live(home)
    identity = adapter.parse_identity(home, blob)
    return blob, identity


@click.group(
    cls=LairenGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="lairen")
def cli() -> None:
    """Manage CLI-agent accounts, holder homes, and deployments."""


@cli.group(name="account")
def account_group() -> None:
    """Manage account identity, stored auth, and the holder home."""


@account_group.command("add")
@click.option(
    "--provider",
    "provider_name",
    required=True,
    type=click.Choice(sorted(PROVIDERS)),
    help="provider that owns the credential",
)
@click.option(
    "--home",
    required=True,
    type=click.Path(path_type=Path),
    help="existing, pre-logged-in provider home",
)
@click.option("--alias", "alias_name", help="stable short handle for the account")
@click.option("--label", help="override the display label")
@click.option("--holder-only", is_flag=True, help="record the holder without storing auth")
@click.option("--no-holder", is_flag=True, help="store auth without recording a holder")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_add(
    provider_name: str,
    home: Path,
    alias_name: str | None,
    label: str | None,
    holder_only: bool,
    no_holder: bool,
    json_output: bool,
) -> None:
    """Create or refresh an account from a live provider home."""
    if holder_only and no_holder:
        raise LairenError("--holder-only and --no-holder cannot be combined")
    paths, registry, store = _context()
    adapter = get_provider(provider_name)
    _warn_experimental(provider_name)
    home_path = adapter.resolve_home(home).resolve()
    if not home_path.is_dir():
        raise LairenError(f"home is not a directory: {home_path}")
    blob, identity = _read_home_identity(adapter, home_path)
    existing = registry.get(adapter.name, identity.id)
    now = utc_now()

    alias = existing.alias if existing is not None else None
    if alias_name is not None:
        alias = registry.validate_alias(alias_name, adapter.name, identity.id)

    if existing is None:
        record = Account(
            provider=adapter.name,
            id=identity.id,
            label=label or identity.label,
            alias=alias,
            extra=identity.extra,
        )
    else:
        record = existing
        if label is not None:
            record.label = label
        elif _label_tracks_identity(record, identity.id):
            record.label = identity.label
        record.extra = identity.extra

    if not holder_only:
        store.set(adapter.name, identity.id, blob)
        record.auth = Auth(
            stored=True,
            captured_at=now,
            source_home=str(home_path),
        )
    if not no_holder:
        record.holder = Holder(
            home=str(home_path),
            recorded_at=now,
            verified_at=now,
        )

    registry.upsert(record)
    payload = _account_payload(record, store, [])
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(
        f"account {record.ref}  alias={record.alias or '-'}  "
        f"auth={payload['auth']['present'] and 'stored' or 'none'}  "
        f"holder={record.holder.home if record.holder else '-'}  "
        f"state={payload['holder_state']}"
    )


@account_group.command("list")
@click.option(
    "--provider",
    "provider_names",
    multiple=True,
    type=click.Choice(sorted(PROVIDERS)),
    help="limit to one provider (repeatable)",
)
@click.option("--available", is_flag=True, help="only accounts with no active deployment")
@click.option("--with-holder", is_flag=True, help="only accounts with a holder home")
@click.option("--stale-holders", is_flag=True, help="only accounts with a stale holder")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_list(
    provider_names: tuple[str, ...],
    available: bool,
    with_holder: bool,
    stale_holders: bool,
    json_output: bool,
) -> None:
    """List accounts with auth, holder, and deployment summary."""
    paths, registry, store = _context()
    accounts = registry.list()
    if provider_names:
        allowed = set(provider_names)
        accounts = [item for item in accounts if item.provider in allowed]
    if with_holder:
        accounts = [item for item in accounts if item.holder is not None]
    if stale_holders:
        accounts = [
            item
            for item in accounts
            if holder_state(item.provider, item.holder) == "possibly-stale"
        ]

    by_ref = _associations_by_ref(accounts, paths)
    if available:
        accounts = [
            item
            for item in accounts
            if not _active_deployments(by_ref.get(item.ref, []))
        ]
        by_ref = _associations_by_ref(accounts, paths)

    if json_output:
        click.echo(
            json.dumps(
                [
                    _account_payload(item, store, by_ref.get(item.ref, []))
                    for item in accounts
                ],
                indent=2,
            )
        )
        return

    if not accounts:
        click.echo("no accounts; run `lairen account add --provider PROVIDER --home PATH`")
        return

    rows = [
        (
            item.ref,
            item.alias or "-",
            item.label,
            _auth_cell(item, store),
            _holder_cell(item),
            holder_state(item.provider, item.holder),
            _deployment_summary(by_ref.get(item.ref, [])),
        )
        for item in accounts
    ]
    _print_table(
        ("REF", "ALIAS", "LABEL", "AUTH", "HOLDER", "HOLDER STATE", "DEPLOYED"),
        rows,
    )


@account_group.command("show")
@click.argument("ref")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_show(ref: str, json_output: bool) -> None:
    """Show one account, its auth, holder, and deployments."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    associations = _associations_by_ref([record], paths).get(record.ref, [])
    payload = _account_payload(record, store, associations)
    blob = store.get(record.provider, record.id)
    if blob is not None:
        try:
            payload["auth"]["usage"] = adapter.local_usage(blob)
        except LairenError as exc:
            payload["auth"]["error"] = str(exc)
    if record.holder is not None:
        holder_home = Path(record.holder.home).expanduser()
        live: dict[str, Any] = {"state": payload["holder_state"]}
        try:
            live_blob, live_identity = _read_home_identity(adapter, holder_home)
        except (OSError, LairenError, UnicodeDecodeError) as exc:
            live["error"] = str(exc)
        else:
            live.update(
                {
                    "identity": {
                        "id": live_identity.id,
                        "label": live_identity.label,
                        "extra": live_identity.extra,
                    },
                    "usage": adapter.local_usage(live_blob),
                }
            )
        payload["holder"]["live"] = live

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"account : {record.ref}")
    click.echo(f"alias   : {record.alias or '-'}")
    click.echo(f"label   : {record.label}")
    auth = payload["auth"]
    if auth["present"]:
        click.echo(
            f"auth    : stored  captured={auth['captured_at'] or '-'}  "
            f"source={auth['source_home'] or '-'}"
        )
        usage = auth.get("usage") or {}
        expires = usage.get("access_token_expires_at")
        if isinstance(expires, (int, float)):
            remaining = int(float(expires) - time.time())
            click.echo(
                f"access  : {epoch_to_iso(expires) or '-'}  ({format_remaining(remaining)})"
            )
    elif auth["stored"]:
        click.echo("auth    : missing from the credential store")
    else:
        click.echo("auth    : none")
    if record.holder is not None:
        click.echo(
            f"holder  : {record.holder.home}  "
            f"state={payload['holder_state']}"
        )
        if record.holder.verified_at:
            click.echo(f"verified: {record.holder.verified_at}")
        if record.holder.stale_since:
            click.echo(
                f"stale   : {record.holder.stale_since}  "
                f"{record.holder.stale_reason or ''}"
            )
    else:
        click.echo("holder  : none")
    if associations:
        click.echo("deployments:")
        rows = [
            (
                item.mode,
                item.home,
                item.state,
                item.project or "-",
                item.deployed_at or "-",
            )
            for item in sorted(
                associations,
                key=lambda entry: (entry.deployed_at or "", entry.home),
                reverse=True,
            )
        ]
        _print_table(("MODE", "HOME", "STATE", "PROJECT", "DEPLOYED AT"), rows)


@account_group.command("update")
@click.argument("ref")
@click.option(
    "--home",
    required=True,
    type=click.Path(path_type=Path),
    help="provider home to read the new credential from",
)
@click.option("--label", help="override the display label")
@click.option("--keep-home", is_flag=True, help="keep the existing holder home")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_update(
    ref: str,
    home: Path,
    label: str | None,
    keep_home: bool,
    json_output: bool,
) -> None:
    """Rebind an account to a new home, refreshing auth and holder."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    _warn_experimental(record.provider)
    home_path = adapter.resolve_home(home).resolve()
    blob, identity = _read_home_identity(adapter, home_path)
    old_id = record.id
    old_ref = record.ref
    new_id = identity.id

    if new_id != old_id:
        existing = registry.get(adapter.name, new_id)
        if existing is not None:
            raise LairenError(
                f"the credential at {home_path} belongs to existing account "
                f"{existing.ref}; remove or update that account instead"
            )
        for other in registry.list():
            if other.alias == new_id and (other.provider, other.id) != (
                record.provider,
                old_id,
            ):
                raise LairenError(
                    f"new account id {new_id!r} conflicts with alias of {other.ref}"
                )
        if keep_home:
            raise LairenError(
                "--keep-home cannot be used when the identity changes; "
                "the new home becomes the holder"
            )

    if label is not None:
        record.label = label
    elif _label_tracks_identity(record, old_id):
        record.label = identity.label
    record.id = new_id
    record.extra = identity.extra
    now = utc_now()
    store.set(record.provider, new_id, blob)
    record.auth = Auth(stored=True, captured_at=now, source_home=str(home_path))
    if not keep_home:
        record.holder = Holder(
            home=str(home_path),
            recorded_at=now,
            verified_at=now,
        )
    registry.replace(record.provider, old_id, record)
    if new_id != old_id:
        store.delete(record.provider, old_id)
    _record_deployment(
        paths,
        "update",
        record,
        source_home=str(home_path),
        previous_ref=old_ref if new_id != old_id else None,
        mode="update",
    )

    if json_output:
        click.echo(json.dumps(_account_payload(record, store, []), indent=2))
        return
    if new_id == old_id:
        click.echo(f"updated {record.ref}  source={home_path}")
    else:
        click.echo(f"updated {old_ref} -> {record.ref}  source={home_path}")
    if record.alias:
        click.echo(f"alias: {record.alias}")


@account_group.command("sync")
@click.argument("refs", nargs=-1)
@click.option(
    "--home",
    "homes",
    multiple=True,
    type=click.Path(path_type=Path),
    help="provider home to read (repeatable); restricts sync to these homes",
)
@click.option(
    "--holder-only",
    is_flag=True,
    help="read only the account holder home",
)
@click.option("--dry-run", is_flag=True, help="report what would change without writing")
@click.option(
    "--strict",
    is_flag=True,
    help="exit 1 when a drift remains or a source cannot be used",
)
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_sync(
    refs: tuple[str, ...],
    homes: tuple[Path, ...],
    holder_only: bool,
    dry_run: bool,
    strict: bool,
    json_output: bool,
) -> None:
    """Pull fresher auth from the holder or deployed homes into the store."""
    paths, registry, store = _context()
    if homes and not refs:
        raise LairenError("--home requires a REF")
    if homes and len(refs) > 1:
        raise LairenError("--home accepts only one REF")
    if holder_only and homes:
        raise LairenError("--holder-only and --home cannot be combined")

    accounts = [registry.resolve(ref) for ref in refs] if refs else registry.list()
    records: list[dict[str, Any]] = []
    pending = 0
    problems = 0

    for record in accounts:
        adapter = get_provider(record.provider)
        _warn_experimental(record.provider)
        stored = store.get(record.provider, record.id)
        candidates = candidate_homes(
            paths,
            record,
            extra_homes=tuple(homes),
            include_known=not homes,
            holder_only=holder_only,
        )
        plan = plan_sync(record, stored, adapter, candidates)
        for problem in plan.problems:
            click.echo(f"warning: {problem}", err=True)
            problems += 1
        for note in plan.notes:
            click.echo(f"note: {note}", err=True)

        item: dict[str, Any] = {
            "ref": record.ref,
            "provider": record.provider,
            "alias": record.alias,
            "state": plan.state,
            "home": str(plan.home) if plan.home else None,
            "old_access_expires_at": epoch_to_iso(plan.old_access_expires_at),
            "new_access_expires_at": epoch_to_iso(plan.new_access_expires_at),
            "problems": list(plan.problems),
            "notes": list(plan.notes),
        }

        holder_home = (
            Path(record.holder.home).expanduser().resolve()
            if record.holder is not None and record.holder.home
            else None
        )
        holder_read = holder_home is not None and holder_home in candidates

        if plan.state == "update":
            old = epoch_to_iso(plan.old_access_expires_at) or "none"
            new = epoch_to_iso(plan.new_access_expires_at) or "unknown"
            if dry_run:
                if not json_output:
                    click.echo(
                        f"would update {record.ref} from {plan.home}: access {old} -> {new}"
                    )
                pending += 1
            else:
                apply_sync(paths, store, plan)
                registry.upsert(record)
                if not json_output:
                    click.echo(
                        f"updated {record.ref} from {plan.home}: access {old} -> {new}"
                    )
        elif plan.state in ("no-known-homes", "no-usable-homes"):
            if stored is None:
                problems += 1
            if not json_output:
                click.echo(f"no usable homes for {record.ref}")
        else:
            if not dry_run and holder_read and record.holder is not None:
                if record.holder.stale_since:
                    clear_holder_stale(record.holder)
                    record.holder.verified_at = utc_now()
                    registry.upsert(record)
            if not json_output:
                click.echo(f"current {record.ref}")
        records.append(item)

    if json_output:
        click.echo(json.dumps(records, indent=2))
    if strict and (problems or pending):
        raise LairenError(f"strict sync failed: {problems + pending} issue(s) remain")


@account_group.command("set-home")
@click.argument("ref")
@click.option(
    "--home",
    required=True,
    type=click.Path(path_type=Path),
    help="live provider home to attach",
)
@click.option("--sync", "do_sync", is_flag=True, help="also capture auth from the home")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_set_home(
    ref: str,
    home: Path,
    do_sync: bool,
    json_output: bool,
) -> None:
    """Attach or replace an account's holder home."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    _warn_experimental(record.provider)
    home_path = Path(home).expanduser().resolve()
    if not home_path.is_dir():
        raise LairenError(f"holder home is not a directory: {home_path}")
    blob, identity = _read_home_identity(adapter, home_path)
    if identity.id != record.id:
        raise LairenError(
            f"{home_path} holds {adapter.name}/{identity.id}, not {record.ref}; "
            f"run `lairen account update {record.ref} --home {home_path}`"
        )
    now = utc_now()
    record.holder = Holder(
        home=str(home_path),
        recorded_at=now,
        verified_at=now,
    )
    if do_sync:
        store.set(record.provider, record.id, blob)
        record.auth = Auth(
            stored=True,
            captured_at=now,
            source_home=str(home_path),
        )
    registry.upsert(record)
    _record_deployment(
        paths,
        "set-home",
        record,
        home=str(home_path),
        source_home=str(home_path),
        mode="holder",
    )
    if json_output:
        click.echo(json.dumps(_account_payload(record, store, []), indent=2))
        return
    click.echo(f"holder {record.ref} -> {home_path}")
    if do_sync:
        click.echo(f"synced auth from {home_path}")


@account_group.command("clear-home")
@click.argument("ref")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_clear_home(ref: str, json_output: bool) -> None:
    """Forget an account's holder home; stored auth is kept."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    if record.holder is None:
        raise LairenError(f"{record.ref} has no holder home")
    old_home = record.holder.home
    record.holder = None
    registry.upsert(record)
    _record_deployment(
        paths,
        "clear-home",
        record,
        source_home=old_home,
        mode="holder",
    )
    if json_output:
        click.echo(json.dumps(_account_payload(record, store, []), indent=2))
        return
    click.echo(f"cleared holder for {record.ref}  (home left untouched: {old_home})")


@account_group.command("alias")
@click.argument("ref", required=False)
@click.argument("name", required=False)
@click.option("--clear", "clear_alias", is_flag=True, help="remove the alias from REF")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_alias(
    ref: str | None,
    name: str | None,
    clear_alias: bool,
    json_output: bool,
) -> None:
    """Set, clear, or list stable account aliases."""
    _, registry, _ = _context()
    if ref is None:
        if name or clear_alias:
            raise LairenError("provide REF when setting or clearing an alias")
        aliases = [
            {"ref": record.ref, "alias": record.alias}
            for record in registry.list()
            if record.alias
        ]
        if json_output:
            click.echo(json.dumps(aliases, indent=2))
            return
        if not aliases:
            click.echo("no aliases; run `lairen account alias <ref> <name>`")
            return
        _print_table(
            ("ALIAS", "REF"),
            [(item["alias"], item["ref"]) for item in aliases],
        )
        return

    record = registry.resolve(ref)
    if clear_alias:
        if name:
            raise LairenError("cannot combine a name with --clear")
        if not record.alias:
            raise LairenError(f"{record.ref} has no alias")
        registry.clear_alias(record.provider, record.id)
        click.echo(f"cleared alias for {record.ref}")
        return
    if name is None:
        if json_output:
            click.echo(json.dumps({"ref": record.ref, "alias": record.alias}, indent=2))
        elif record.alias:
            click.echo(record.alias)
        else:
            click.echo(f"{record.ref} has no alias")
        return
    updated = registry.set_alias(record.provider, record.id, name)
    click.echo(f"aliased {updated.ref} -> {updated.alias}")


@account_group.command("usage")
@click.argument("refs", nargs=-1)
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_usage(refs: tuple[str, ...], json_output: bool) -> None:
    """Show expiry and usage statistics (alias: stats)."""
    _, registry, store = _context()
    accounts = [registry.resolve(ref) for ref in refs] if refs else registry.list()
    if not accounts:
        click.echo("no accounts; run `lairen account add --provider PROVIDER --home PATH`")
        return

    records: list[dict[str, Any]] = []
    for record in accounts:
        item: dict[str, Any] = {
            "ref": record.ref,
            "provider": record.provider,
            "alias": record.alias,
            "label": record.label,
            "holder": record.holder.home if record.holder else None,
            "holder_state": holder_state(record.provider, record.holder),
        }
        blob = store.get(record.provider, record.id)
        if blob is None:
            item["error"] = "credential blob missing"
            records.append(item)
            continue
        usage_data = get_provider(record.provider).local_usage(blob)
        expires_at = usage_data.get("access_token_expires_at")
        remaining: int | None = None
        if isinstance(expires_at, (int, float)):
            remaining = int(float(expires_at) - time.time())
        item.update(
            {
                "expires_at": epoch_to_iso(expires_at),
                "expires_in_seconds": remaining,
                "expires_in": format_remaining(remaining),
                "usage": usage_data,
            }
        )
        records.append(item)

    if json_output:
        click.echo(json.dumps(records, indent=2))
        return

    rows = [
        (
            item["ref"],
            item.get("expires_at") or "-",
            item.get("expires_in") or "-",
            item.get("holder_state") or "-",
        )
        for item in records
    ]
    _print_table(("REF", "ACCESS EXPIRES (UTC)", "REMAINING", "HOLDER STATE"), rows)


account_group.add_command(account_usage, "stats")


@account_group.command("scan")
@click.argument(
    "directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option(
    "--depth",
    type=click.IntRange(min=0),
    default=1,
    show_default=True,
    help="directory levels below the scan root",
)
@click.option(
    "--provider",
    "provider_filter",
    multiple=True,
    type=click.Choice(["codex", "kimi"]),
    help="limit the scan to a provider (repeatable)",
)
@click.option("--add", "do_add", is_flag=True, help="create accounts for discovered homes")
@click.option("--holder-only", is_flag=True, help="add holders without storing auth")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_scan(
    directory: Path,
    depth: int,
    provider_filter: tuple[str, ...],
    do_add: bool,
    holder_only: bool,
    json_output: bool,
) -> None:
    """Scan a directory tree for Codex and Kimi credential homes."""
    providers = provider_filter or ("codex", "kimi")
    hits = scan_accounts(directory, depth=depth, providers=providers)
    if not hits:
        click.echo(f"no accounts found under {directory} (depth={depth})")
        return

    if do_add:
        _, registry, store = _context()
        for hit in best_per_account(hits):
            existing = registry.get(hit.provider, hit.identity.id)
            record = existing or Account(
                provider=hit.provider,
                id=hit.identity.id,
                label=hit.identity.label,
                extra=hit.identity.extra,
            )
            record.extra = hit.identity.extra
            now = utc_now()
            if not holder_only:
                store.set(hit.provider, hit.identity.id, hit.credential.read_text(encoding="utf-8"))
                record.auth = Auth(
                    stored=True,
                    captured_at=now,
                    source_home=str(hit.home),
                )
            record.holder = Holder(
                home=str(hit.home),
                recorded_at=now,
                verified_at=now,
            )
            registry.upsert(record)
            click.echo(
                f"account {record.ref}  auth={'none' if holder_only else 'stored'}  "
                f"holder={hit.home}"
            )
        return

    if json_output:
        click.echo(
            json.dumps(
                [
                    {
                        "provider": hit.provider,
                        "ref": hit.ref,
                        "label": hit.identity.label,
                        "home": str(hit.home),
                        "credential": str(hit.credential),
                        "depth": hit.depth,
                    }
                    for hit in hits
                ],
                indent=2,
            )
        )
        return

    rows = [(hit.provider, hit.ref, str(hit.home), hit.depth) for hit in hits]
    _print_table(("PROVIDER", "REF", "HOME", "DEPTH"), rows)


@account_group.command("remove")
@click.argument("ref")
@click.option("--yes", is_flag=True, help="confirm removal")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def account_remove(ref: str, yes: bool, json_output: bool) -> None:
    """Remove an account and its stored auth; homes and links are untouched."""
    if not yes:
        raise LairenError("refusing to remove without --yes")
    paths, registry, store = _context()
    record = registry.resolve(ref)
    associations = _associations_by_ref([record], paths).get(record.ref, [])
    links = [item for item in associations if item.mode == "link" and item.state == "active"]
    if links:
        for item in links:
            click.echo(
                f"warning: {item.home} still links to this account's holder",
                err=True,
            )
    payload = _account_payload(record, store, associations)
    store.delete(record.provider, record.id)
    registry.remove(record.provider, record.id)
    _record_deployment(
        paths,
        "remove",
        record,
        source_home=record.source_home or (record.holder.home if record.holder else None),
        mode="remove",
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(f"removed {record.ref}")


@cli.group(name="deploy")
def deploy_group() -> None:
    """Materialize an account into a project home or the current shell."""


@deploy_group.command("copy")
@click.argument("ref")
@click.option(
    "--project",
    type=click.Path(path_type=Path),
    help="project root used for attribution and relative --home resolution",
)
@click.option(
    "--home",
    type=click.Path(path_type=Path),
    help="target provider home; defaults to <project>/<provider native name>",
)
@click.option("--sync", "do_sync", is_flag=True, help="sync fresher auth before writing")
@click.option("--force", is_flag=True, help="overwrite a target with a newer credential")
@click.option("--no-backup", is_flag=True, help="skip the pre-deploy snapshot")
def deploy_copy(
    ref: str,
    project: Path | None,
    home: Path | None,
    do_sync: bool,
    force: bool,
    no_backup: bool,
) -> None:
    """Copy stored auth into a project home."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    _warn_experimental(record.provider)
    blob = _load_stored_blob(record, store)

    if do_sync:
        candidates = candidate_homes(paths, record, include_known=True)
        plan = plan_sync(record, blob, adapter, candidates)
        for problem in plan.problems:
            click.echo(f"warning: {problem}", err=True)
        for note in plan.notes:
            click.echo(f"note: {note}", err=True)
        if plan.state == "update" and plan.blob is not None:
            apply_sync(paths, store, plan)
            blob = plan.blob
            registry.upsert(record)
            old = epoch_to_iso(plan.old_access_expires_at) or "none"
            new = epoch_to_iso(plan.new_access_expires_at) or "unknown"
            click.echo(f"synced {record.ref} from {plan.home}: access {old} -> {new}")

    target = resolve_deploy_target(adapter, project, home)
    target_home = target.home
    if home is None:
        click.echo(f"target: {target_home}")
    warning = foreign_home_warning(adapter, target_home)
    if warning:
        click.echo(f"warning: {warning}", err=True)
    target_path = adapter.credential_path_for(target_home)

    if target_path.exists():
        check = check_overwrite(
            store,
            adapter,
            target_home,
            target_path,
            record.ref,
            registry=registry,
        )
        if check.blocked:
            reason = check.reason or "the target holds a newer credential"
            advice = check.advice or "Run `lairen account sync` first."
            if not force:
                raise LairenError(
                    f"refusing to overwrite {target_path}: {reason}.\n"
                    f"{advice}\n"
                    "Pass --force to overwrite anyway."
                )
            click.echo(f"warning: overwriting {target_path}: {reason}", err=True)
        elif check.warning:
            click.echo(f"warning: {check.warning}", err=True)

    snapshot: Path | None = None
    if target_path.exists() and not no_backup:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = paths.snapshots_dir / f"{record.provider}-{stamp}" / adapter.CREDENTIAL_RELPATH
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, snapshot)
        os.chmod(snapshot, 0o600)

    written = adapter.deploy(target_home, blob)
    holder_home = (
        Path(record.holder.home).expanduser().resolve()
        if record.holder is not None
        else None
    )
    if record.holder is not None and holder_home is not None:
        if target_home == holder_home:
            clear_holder_stale(record.holder)
            record.holder.verified_at = utc_now()
            click.echo(
                "note: target is the holder home; stored auth replaced the live holder",
                err=True,
            )
        else:
            mark_holder_stale(
                record.holder,
                f"deploy copy -> {target_home}",
            )
            click.echo(
                f"note: holder {holder_home} is now possibly stale; "
                f"run `lairen account sync {record.ref} --home {holder_home}` to refresh it",
                err=True,
            )
    registry.upsert(record)
    _record_deployment(
        paths,
        "deploy",
        record,
        home=str(target_home),
        source_home=record.source_home,
        project=target.project,
        mode="copy",
    )
    click.echo(f"deployed {record.ref} -> {written}")
    if snapshot is not None:
        click.echo(f"snapshot: {snapshot}")


@deploy_group.command("link")
@click.argument("ref")
@click.option(
    "--project",
    type=click.Path(path_type=Path),
    help="project root used for attribution and relative --home resolution",
)
@click.option(
    "--home",
    type=click.Path(path_type=Path),
    help="link path; defaults to <project>/<provider native name>",
)
@click.option("--force", is_flag=True, help="replace an existing symlink")
def deploy_link(
    ref: str,
    project: Path | None,
    home: Path | None,
    force: bool,
) -> None:
    """Symlink a project home to the account's holder home."""
    paths, registry, store = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    _warn_experimental(record.provider)
    if record.holder is None or not record.holder.home:
        raise LairenError(
            f"{record.ref} has no holder home; "
            f"run `lairen account set-home {record.ref} --home PATH`"
        )
    holder_home = Path(record.holder.home).expanduser().resolve()
    if not holder_home.is_dir():
        raise LairenError(f"holder home is missing: {holder_home}")

    target = resolve_link_target(adapter, project, home)
    target_home = target.home
    warning = foreign_home_warning(adapter, target_home)
    if warning:
        click.echo(f"warning: {warning}", err=True)
    if target_home == holder_home:
        raise LairenError(
            f"{target_home} is already the holder home; choose another target"
        )

    if target_home.is_symlink():
        current = Path(os.path.realpath(target_home))
        if current == holder_home:
            click.echo(f"already linked {record.ref} -> {target_home}")
            return
        if not force:
            raise LairenError(
                f"{target_home} is a symlink to {current}; pass --force to replace it"
            )
        target_home.unlink()
    elif target_home.exists():
        raise LairenError(
            f"{target_home} exists and is not a symlink; move it aside before linking"
        )

    state = holder_state(record.provider, record.holder)
    if state == "possibly-stale":
        click.echo(
            f"warning: holder {holder_home} is possibly stale; "
            f"run `lairen account sync {record.ref} --home {holder_home}`",
            err=True,
        )
    target_home.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(holder_home, target_home, target_is_directory=True)
    _record_deployment(
        paths,
        "link",
        record,
        home=str(target_home),
        source_home=str(holder_home),
        project=target.project,
        mode="link",
    )
    click.echo(f"linked {record.ref} -> {target_home}  home={holder_home}")


@deploy_group.command("env")
@click.argument("ref")
@click.option(
    "--shell",
    type=click.Choice(SHELL_CHOICES),
    help="shell syntax (default: auto-detect)",
)
def deploy_env(ref: str, shell: str | None) -> None:
    """Print shell exports that point the provider home at the holder."""
    _, registry, _ = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    if not adapter.env_var:
        raise LairenError(
            f"{record.provider} has no provider home environment variable; "
            "use `lairen deploy link` instead"
        )
    if record.holder is None or not record.holder.home:
        raise LairenError(
            f"{record.ref} has no holder home; "
            f"run `lairen account set-home {record.ref} --home PATH`"
        )
    holder_home = Path(record.holder.home).expanduser().resolve()
    if not holder_home.is_dir():
        raise LairenError(f"holder home is missing: {holder_home}")
    state = holder_state(record.provider, record.holder)
    if state == "possibly-stale":
        click.echo(
            f"warning: holder {holder_home} is possibly stale; "
            f"run `lairen account sync {record.ref} --home {holder_home}`",
            err=True,
        )
    resolved = normalize_shell(shell or "auto")
    click.echo(export_command(resolved, adapter.env_var, str(holder_home)))


@deploy_group.command("list")
@click.option(
    "--group-by",
    type=click.Choice(("account", "project")),
    default="account",
    show_default=True,
    help="group the rows by account or by project",
)
@click.option(
    "--account",
    "account_refs",
    multiple=True,
    help="limit to one account ref (repeatable)",
)
@click.option(
    "--project",
    "project_paths",
    multiple=True,
    type=click.Path(path_type=Path),
    help="limit to one project directory (repeatable)",
)
@click.option(
    "--provider",
    "provider_names",
    multiple=True,
    type=click.Choice(sorted(PROVIDERS)),
    help="limit to one provider (repeatable)",
)
@click.option(
    "--mode",
    "modes",
    multiple=True,
    type=click.Choice(("copy", "link")),
    help="limit to one deployment mode (repeatable)",
)
@click.option("--active-only", is_flag=True, help="hide overwritten assignments")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def deploy_list(
    group_by: str,
    account_refs: tuple[str, ...],
    project_paths: tuple[Path, ...],
    provider_names: tuple[str, ...],
    modes: tuple[str, ...],
    active_only: bool,
    json_output: bool,
) -> None:
    """List account/project deployments from the ledger."""
    paths, registry, _ = _context()
    accounts = (
        [registry.resolve(ref) for ref in account_refs]
        if account_refs
        else registry.list()
    )
    items = build_associations(accounts, DeploymentLog(paths.deployments_path))

    if provider_names:
        allowed = set(provider_names)
        items = [item for item in items if item.provider in allowed]
    if modes:
        allowed_modes = set(modes)
        items = [item for item in items if item.mode in allowed_modes]
    if project_paths:
        wanted = {str(path.expanduser().resolve()) for path in project_paths}
        items = [
            item
            for item in items
            if item.project and str(Path(item.project).resolve()) in wanted
        ]
    if active_only:
        items = [item for item in items if item.state == "active"]

    if json_output:
        click.echo(json.dumps([item.to_dict() for item in items], indent=2))
        return
    _render_deployments(items, group_by)


def _deployment_key(item: Association, group_by: str) -> str:
    if group_by == "account":
        return item.ref
    return item.project or "(unattributed)"


def _render_deployments(items: list[Association], group_by: str) -> None:
    if not items:
        click.echo("no deployments recorded")
        return

    groups: dict[str, list[Association]] = {}
    for item in items:
        groups.setdefault(_deployment_key(item, group_by), []).append(item)

    for position, key in enumerate(sorted(groups)):
        if position:
            click.echo()
        group = groups[key]
        rows: list[tuple[Any, ...]]
        if group_by == "account":
            alias = group[0].alias
            click.echo(f"{key}" + (f"  alias={alias}" if alias else ""))
            rows = [
                (
                    item.mode,
                    item.project or "(unattributed)",
                    item.home,
                    item.deployed_at or "-",
                    item.state,
                )
                for item in sorted(
                    group,
                    key=lambda entry: (
                        entry.deployed_at or "",
                        entry.project or "",
                        entry.home,
                    ),
                    reverse=True,
                )
            ]
            _print_table(("MODE", "PROJECT", "HOME", "DEPLOYED AT", "STATE"), rows)
        else:
            click.echo(key)
            rows = [
                (
                    item.ref,
                    item.alias or "-",
                    item.mode,
                    item.home,
                    item.deployed_at or "-",
                    item.state,
                )
                for item in sorted(
                    group,
                    key=lambda entry: (
                        entry.deployed_at or "",
                        entry.ref,
                        entry.home,
                    ),
                    reverse=True,
                )
            ]
            _print_table(
                ("ACCOUNT", "ALIAS", "MODE", "HOME", "DEPLOYED AT", "STATE"),
                rows,
            )


@deploy_group.command("unlink")
@click.argument("ref")
@click.option(
    "--project",
    type=click.Path(path_type=Path),
    help="project root used for relative --home resolution",
)
@click.option(
    "--home",
    type=click.Path(path_type=Path),
    help="link path; defaults to <project>/<provider native name>",
)
@click.option("--yes", is_flag=True, help="confirm removal")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def deploy_unlink(
    ref: str,
    project: Path | None,
    home: Path | None,
    yes: bool,
    json_output: bool,
) -> None:
    """Remove a project symlink that points at the account holder."""
    if not yes:
        raise LairenError("refusing to unlink without --yes")
    paths, registry, _ = _context()
    record = registry.resolve(ref)
    adapter = get_provider(record.provider)
    if record.holder is None or not record.holder.home:
        raise LairenError(f"{record.ref} has no holder home")
    holder_home = Path(record.holder.home).expanduser().resolve()
    target = resolve_link_target(adapter, project, home)
    target_home = target.home
    if not target_home.is_symlink():
        raise LairenError(f"{target_home} is not a symlink")
    current = Path(os.path.realpath(target_home))
    if current != holder_home:
        raise LairenError(
            f"{target_home} points to {current}, not holder {holder_home}; refusing"
        )
    target_home.unlink()
    _record_deployment(
        paths,
        "unlink",
        record,
        home=str(target_home),
        source_home=str(holder_home),
        project=target.project,
        mode="link",
    )
    if json_output:
        click.echo(
            json.dumps(
                {
                    "ref": record.ref,
                    "home": str(target_home),
                    "holder": str(holder_home),
                },
                indent=2,
            )
        )
        return
    click.echo(f"unlinked {target_home}  holder={holder_home}")


def _other_projects(item) -> str:
    names: list[str] = []
    for lease in item.leases:
        label = lease.project or lease.home
        if lease.live is False:
            label = f"{label} (overwritten)"
        if lease.mode == "link":
            label = f"{label} (link)"
        if label not in names:
            names.append(label)
    return ", ".join(names) if names else "-"


def _render_status(report: ProjectReport) -> None:
    click.echo(f"project: {report.project}")
    for binding in report.shell:
        click.echo(
            f"shell: {binding.env_var}={binding.home}  "
            f"account={binding.ref}  holder_state={binding.holder_state}"
        )
    if not report.accounts:
        click.echo("no provider homes found (looked for .codex, .kimi-code)")
    else:
        rows: list[tuple[Any, ...]] = []
        for item in report.accounts:
            expires = (
                format_remaining(item.expires_in_seconds)
                if item.expires_in_seconds is not None
                else "-"
            )
            alias = _style_alias(item.alias) if item.alias else "-"
            rows.append(
                (
                    item.ref or "-",
                    alias,
                    item.source,
                    item.state,
                    item.holder_state,
                    expires,
                    _other_projects(item),
                )
            )
        _print_table(
            (
                "ACCOUNT",
                "ALIAS",
                "SOURCE",
                "AUTH",
                "HOLDER STATE",
                "ACCESS EXPIRES",
                "OTHER PROJECTS",
            ),
            rows,
        )
        for item in report.accounts:
            if item.source == "link":
                click.echo(f"linked: {item.link} -> {item.home}")
            if item.state == "invalid":
                click.echo(f"invalid: {item.credential}: {item.error}")
            elif item.state == "unregistered":
                click.echo(f"unregistered: {item.ref}  {item.credential}")
                click.echo(
                    f"  register: lairen account add --provider {item.provider} "
                    f"--home {item.home}"
                )
            elif item.state == "drifted":
                click.echo(f"drifted: {item.ref}  project credential differs from stored auth")
            elif item.state == "missing-auth":
                click.echo(f"missing auth: {item.ref} has no stored copy")
            if item.holder_state in ("possibly-stale", "missing", "no-login"):
                reason = f"  ({item.holder_reason})" if item.holder_reason else ""
                click.echo(f"holder {item.holder_state}: {item.holder}{reason}")
    for problem in report.problems:
        click.echo(f"warning: {problem.message}", err=True)


@cli.command()
@click.argument(
    "directory",
    required=False,
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option(
    "--provider",
    "provider_filter",
    multiple=True,
    type=click.Choice(["codex", "kimi"]),
    help="limit the report to a provider (repeatable)",
)
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
@click.option(
    "--strict",
    is_flag=True,
    help="exit 1 when auth or holder state needs attention",
)
def status(
    directory: Path | None,
    provider_filter: tuple[str, ...],
    json_output: bool,
    strict: bool,
) -> None:
    """Show which accounts a project directory is using."""
    paths = Paths.resolve()
    require_current_schema(paths, initialize=False)
    project = directory or Path.cwd()
    report = inspect_project(
        project,
        provider_filter or ("codex", "kimi"),
        paths,
    )
    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        _render_status(report)
    if strict and report.problems:
        raise LairenError(format_problems(report.problems))


@cli.command()
def providers() -> None:
    """Show provider defaults and adapter status."""
    rows = [
        (
            adapter.name,
            "yes" if adapter.tested else "no",
            adapter.env_var or "-",
            str(adapter.default_home()),
            adapter.PROJECT_HOME_NAME or "-",
            str(adapter.CREDENTIAL_RELPATH),
            adapter.deploy_note or "-",
        )
        for adapter in PROVIDERS.values()
    ]
    _print_table(
        ("PROVIDER", "TESTED", "ENV", "DEFAULT HOME", "PROJECT HOME", "CREDENTIAL", "NOTES"),
        rows,
    )


def _render_migration(report: MigrationReport) -> None:
    if report.fresh:
        if report.dry_run:
            click.echo(
                f"would initialize lairen state schema v{report.to_version}"
            )
            click.echo("dry run: no files written")
        else:
            click.echo(f"initialized lairen state schema v{report.to_version}")
        return
    if report.from_version == report.to_version and not report.changed:
        click.echo(f"schema: v{report.to_version} (current); nothing to migrate")
    elif report.from_version == report.to_version:
        click.echo(f"schema: v{report.to_version} (current)")
    else:
        click.echo(f"schema: v{report.from_version} -> v{report.to_version}")
    if report.changed or report.from_version != report.to_version:
        click.echo(f"deploy entries : {report.deploy_entries}")
        click.echo(f"link entries   : {report.link_entries}")
        click.echo(f"project filled : {report.project_filled}")
        click.echo(f"legacy pointers: {report.legacy_materialized}")
        click.echo(f"auth backfilled: {report.auth_backfilled}")
        click.echo(f"mode filled    : {report.mode_filled}")
        click.echo(f"unattributed   : {len(report.unattributed)}")
        for ref, home in report.unattributed:
            suffix = f"  {home}" if home else ""
            click.echo(f"  unattributed {ref}{suffix}")
    if report.holder_unset:
        click.echo(f"holder unset   : {len(report.holder_unset)}")
        for ref, home in report.holder_unset:
            click.echo(f"  {ref}  --home {home}")
        click.echo("  fix: lairen account set-home REF --home PATH")
    if report.dry_run:
        click.echo("dry run: no files written")
    elif report.backup_path:
        click.echo(f"backup: {report.backup_path}")


@cli.command()
@click.option("--dry-run", is_flag=True, help="report changes without writing")
@click.option(
    "--project",
    "project_maps",
    multiple=True,
    metavar="HOME=PROJECT",
    help="map a custom home directory to its project (repeatable)",
)
@click.option("--no-backup", is_flag=True, help="skip the pre-migration backup")
def migrate(dry_run: bool, project_maps: tuple[str, ...], no_backup: bool) -> None:
    """Migrate lairen state to the current schema version."""
    paths = Paths.resolve().ensure()
    mapping: dict[str, str] = {}
    for item in project_maps:
        home, separator, project = item.partition("=")
        if not separator or not home.strip() or not project.strip():
            raise LairenError("--project must use HOME=PROJECT")
        mapping[home.strip()] = project.strip()
    report = migrate_state(
        paths,
        mapping,
        dry_run=dry_run,
        backup=not no_backup,
    )
    _render_migration(report)


@cli.command()
def doctor() -> None:
    """Show resolved paths, counts, and provider homes."""
    paths = Paths.resolve()
    registry = Registry(paths.registry_path)
    store = CredentialStore(paths.credentials_path)
    accounts = registry.load()
    holders = [record for record in accounts if record.holder is not None]
    stale = [
        record
        for record in holders
        if holder_state(record.provider, record.holder) == "possibly-stale"
    ]
    click.echo(f"config dir : {paths.config_dir}")
    click.echo(f"data dir   : {paths.data_dir}")
    click.echo(f"state dir  : {paths.state_dir}")
    click.echo(f"schema     : {schema_status(paths)}")
    click.echo(f"accounts   : {len(accounts)}")
    click.echo(f"stored auth: {store.count()}")
    click.echo(f"holders    : {len(holders)}")
    click.echo(f"stale      : {len(stale)}")
    for adapter in PROVIDERS.values():
        home = adapter.resolve_home()
        login = adapter.credential_path_for(home).is_file()
        tested = "yes" if adapter.tested else "no"
        click.echo(
            f"[{adapter.name}] tested={tested} home={home} "
            f"login={'yes' if login else 'no'}"
        )


def _print_manual_topic(slug: str, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(manual_content.topic_payload(slug), indent=2))
        return
    click.echo(manual_content.TOPICS[slug][1])


@cli.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.pass_context
def manual(ctx: click.Context) -> None:
    """Agent-oriented usage manual with examples."""
    if ctx.invoked_subcommand is None:
        _print_manual_topic("overview", False)


@manual.command()
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def overview(json_output: bool) -> None:
    """Purpose, mental model, and the core commands."""
    _print_manual_topic("overview", json_output)


@manual.command()
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def commands(json_output: bool) -> None:
    """Command synopses and examples."""
    _print_manual_topic("commands", json_output)


@manual.command()
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def workflows(json_output: bool) -> None:
    """Task sequences for common operations."""
    _print_manual_topic("workflows", json_output)


@manual.command(name="providers")
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def providers_topic(json_output: bool) -> None:
    """Provider homes, credential paths, and identities."""
    _print_manual_topic("providers", json_output)


@manual.command()
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def storage(json_output: bool) -> None:
    """Registry, credential store, and snapshot locations."""
    _print_manual_topic("storage", json_output)


@manual.command(name="json")
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def json_topic(json_output: bool) -> None:
    """Machine-readable output shapes."""
    _print_manual_topic("json", json_output)


@manual.command()
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def safety(json_output: bool) -> None:
    """Credential-handling and concurrency rules."""
    _print_manual_topic("safety", json_output)


@manual.command(name="all")
@click.option("--json", "json_output", is_flag=True, help="emit structured JSON")
def all_topics(json_output: bool) -> None:
    """Print every manual topic."""
    if json_output:
        click.echo(json.dumps(manual_content.all_payload(), indent=2))
        return
    click.echo(manual_content.all_text())


def main() -> None:
    cli(prog_name="lairen")
