"""Click command-line interface."""

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
from lairen.deployments import record_event
from lairen.errors import LairenError
from lairen.models import Account
from lairen.paths import Paths
from lairen.providers import PROVIDERS, get_provider
from lairen.scan import best_per_account, scan_accounts
from lairen.status import AccountStatus, ProjectReport, inspect_project
from lairen.store import CredentialStore, Registry
from lairen.sync import apply_sync, candidate_homes, plan_sync
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
    previous_ref: str | None = None,
) -> None:
    try:
        record_event(
            paths.deployments_path,
            action,
            account,
            home=home,
            source_home=source_home,
            previous_ref=previous_ref,
        )
    except OSError as exc:
        click.echo(f"warning: cannot write deployment log: {exc}", err=True)


def _other_projects(item: AccountStatus) -> str:
    names: list[str] = []
    for lease in item.leases:
        label = lease.project or lease.home
        if lease.legacy:
            label = f"{label} (last deploy)"
        if lease.live is False:
            label = f"{label} (overwritten)"
        if label not in names:
            names.append(label)
    return ", ".join(names) if names else "-"


def _status_detail(item: AccountStatus) -> None:
    if item.state == "invalid":
        click.echo(f"invalid: {item.credential}: {item.error}")
    elif item.state == "unregistered":
        click.echo(f"unregistered: {item.ref}  {item.credential}")
        click.echo(f"  register: lairen register {item.provider} --home {item.home}")
    elif item.state == "drifted":
        if item.registry_expires_at == item.expires_at:
            click.echo(f"drifted: {item.ref}  project credential differs from the registry copy")
        else:
            registry = item.registry_expires_at or "unknown"
            click.echo(
                f"drifted: {item.ref}  project expires {item.expires_at}; "
                f"registry expires {registry}"
            )
    elif item.state == "missing-store-blob":
        click.echo(f"missing registry blob: {item.ref}; re-register or update the account")
    elif item.state == "no-login":
        click.echo(f"no login: {item.home}")


def _render_status(report: ProjectReport) -> None:
    click.echo(f"project: {report.project}")
    if not report.accounts:
        click.echo("no provider homes found (looked for .codex, .kimi-code)")
        return

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
                item.provider,
                item.ref or "-",
                alias,
                expires,
                item.state,
                _other_projects(item),
            )
        )
    _print_table(
        ("PROVIDER", "ACCOUNT", "ALIAS", "ACCESS EXPIRES", "STATE", "OTHER PROJECTS"),
        rows,
    )
    for item in report.accounts:
        _status_detail(item)


@click.group(
    cls=LairenGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, prog_name="lairen")
def cli() -> None:
    """Store CLI-agent credentials and deploy them into target homes."""


@cli.command()
@click.argument("provider", type=click.Choice(sorted(PROVIDERS)))
@click.option(
    "--home",
    type=click.Path(path_type=Path),
    help="provider home to read from (falls back to the provider env var or default)",
)
@click.option("--label", help="override the display label")
@click.option("--alias", "alias_name", help="stable short handle for the account")
def register(
    provider: str,
    home: Path | None,
    label: str | None,
    alias_name: str | None,
) -> None:
    """Save the live login from a provider home."""
    adapter = get_provider(provider)
    _warn_experimental(provider)
    home_path = adapter.resolve_home(home)
    blob = adapter.read_live(home_path)
    identity = adapter.parse_identity(home_path, blob)
    _, registry, store = _context()
    alias = registry.validate_alias(alias_name, adapter.name, identity.id) if alias_name else None
    account = Account(
        provider=adapter.name,
        id=identity.id,
        label=label or identity.label,
        source_home=str(home_path),
        alias=alias,
        extra=identity.extra,
    )
    store.set(adapter.name, account.id, blob)
    registry.upsert(account)
    suffix = f"  alias={account.alias}" if account.alias else ""
    click.echo(f"registered {account.ref}  label={account.label}  source={home_path}{suffix}")


@cli.command()
@click.argument("ref")
@click.option(
    "--home",
    required=True,
    type=click.Path(path_type=Path),
    help="provider home to read the new credential from",
)
@click.option("--label", help="override the display label")
def update(ref: str, home: Path, label: str | None) -> None:
    """Replace a saved account's credential from a provider home."""
    paths, registry, store = _context()
    account = registry.resolve(ref)
    adapter = get_provider(account.provider)
    _warn_experimental(account.provider)
    home_path = adapter.resolve_home(home).resolve()
    blob = adapter.read_live(home_path)
    identity = adapter.parse_identity(home_path, blob)
    old_id = account.id
    old_ref = account.ref
    new_id = identity.id

    if new_id != old_id:
        existing = registry.get(account.provider, new_id)
        if existing is not None:
            raise LairenError(
                f"the credential at {home_path} belongs to existing account "
                f"{existing.ref}; remove or update that account instead"
            )
        for other in registry.list():
            if other.alias == new_id and (
                other.provider,
                other.id,
            ) != (account.provider, old_id):
                raise LairenError(f"new account id {new_id!r} conflicts with alias of {other.ref}")

    if label is not None:
        account.label = label
    elif _label_tracks_identity(account, old_id):
        account.label = identity.label
    account.id = new_id
    account.source_home = str(home_path)
    account.extra = identity.extra
    store.set(account.provider, new_id, blob)
    registry.replace(account.provider, old_id, account)
    if new_id != old_id:
        store.delete(account.provider, old_id)
    _record_deployment(
        paths,
        "update",
        account,
        source_home=str(home_path),
        previous_ref=old_ref if new_id != old_id else None,
    )

    suffix = f"  alias={account.alias}" if account.alias else ""
    if new_id == old_id:
        click.echo(f"updated {account.ref}  source={home_path}{suffix}")
    else:
        click.echo(f"updated {old_ref} -> {account.ref}  source={home_path}{suffix}")


@cli.command(name="list")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def list_accounts(json_output: bool) -> None:
    """List saved accounts."""
    _, registry, _ = _context()
    accounts = registry.list()
    if json_output:
        click.echo(
            json.dumps(
                [{"ref": account.ref, **account.to_dict()} for account in accounts],
                indent=2,
            )
        )
        return
    if not accounts:
        click.echo("no accounts; run `lairen register <provider> --home <path>`")
        return
    rows = [
        (
            account.ref,
            account.alias or "-",
            account.label,
            account.source_home or "-",
            account.last_deployed_at or "-",
        )
        for account in accounts
    ]
    _print_table(("REF", "ALIAS", "LABEL", "SOURCE", "LAST DEPLOYED"), rows)


@cli.command()
@click.argument("ref")
def show(ref: str) -> None:
    """Show one account and its local usage metadata."""
    _, registry, store = _context()
    account = registry.resolve(ref)
    blob = store.get(account.provider, account.id)
    if blob is None:
        raise LairenError(f"credential blob missing for {account.ref}")
    adapter = get_provider(account.provider)
    payload = {
        "account": account.to_dict(),
        "usage": adapter.local_usage(blob),
    }
    click.echo(json.dumps(payload, indent=2))


@cli.command()
@click.argument("ref")
@click.option(
    "--home",
    required=True,
    type=click.Path(path_type=Path),
    help="target provider home",
)
@click.option("--no-backup", is_flag=True, help="skip the pre-deploy snapshot")
@click.option(
    "--refresh",
    is_flag=True,
    help="sync refreshed tokens from known homes and the target before writing",
)
def deploy(ref: str, home: Path, no_backup: bool, refresh: bool) -> None:
    """Write a saved credential into a target home."""
    paths, registry, store = _context()
    account = registry.resolve(ref)
    _warn_experimental(account.provider)
    adapter = get_provider(account.provider)
    target_home = adapter.resolve_home(home).resolve()
    target_path = adapter.credential_path_for(target_home)
    blob = store.get(account.provider, account.id)

    if refresh:
        homes = candidate_homes(
            paths,
            account,
            extra_homes=(target_home,) if target_path.exists() else (),
            include_known=True,
        )
        plan = plan_sync(account, blob, adapter, homes)
        for problem in plan.problems:
            click.echo(f"warning: {problem}", err=True)
        for note in plan.notes:
            click.echo(f"note: {note}", err=True)
        if plan.state == "update" and plan.blob is not None:
            apply_sync(paths, store, plan)
            blob = plan.blob
            old = epoch_to_iso(plan.old_access_expires_at) or "unknown"
            new = epoch_to_iso(plan.new_access_expires_at) or "unknown"
            click.echo(f"synced {account.ref} from {plan.home}: access {old} -> {new}")

    if blob is None:
        raise LairenError(f"credential blob missing for {account.ref}")

    snapshot: Path | None = None
    if target_path.exists() and not no_backup:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = paths.snapshots_dir / f"{account.provider}-{stamp}" / adapter.CREDENTIAL_RELPATH
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, snapshot)
        os.chmod(snapshot, 0o600)

    written = adapter.deploy(target_home, blob)
    account.last_deployed_at = utc_now()
    account.last_deployed_home = str(target_home)
    registry.upsert(account)
    _record_deployment(
        paths,
        "deploy",
        account,
        home=str(target_home),
        source_home=account.source_home,
    )
    click.echo(f"deployed {account.ref} -> {written}")
    if snapshot is not None:
        click.echo(f"snapshot: {snapshot}")


@cli.command()
@click.argument("refs", nargs=-1)
@click.option(
    "--home",
    "homes",
    multiple=True,
    type=click.Path(path_type=Path),
    help="provider home to read (repeatable); restricts sync to these homes",
)
@click.option("--dry-run", is_flag=True, help="report what would change without writing")
@click.option(
    "--strict",
    is_flag=True,
    help="exit 1 when a drift remains or a source cannot be used",
)
def sync(
    refs: tuple[str, ...],
    homes: tuple[Path, ...],
    dry_run: bool,
    strict: bool,
) -> None:
    """Pull refreshed credentials from known homes back into the store."""
    paths, registry, store = _context()
    if homes and not refs:
        raise LairenError("--home requires a REF")
    if homes and len(refs) > 1:
        raise LairenError("--home accepts only one REF")

    accounts = [registry.resolve(ref) for ref in refs] if refs else registry.list()
    if not accounts:
        click.echo("no accounts; run `lairen register <provider> --home <path>`")
        return

    extra_homes = tuple(Path(home) for home in homes)
    pending = 0
    problems = 0
    for account in accounts:
        adapter = get_provider(account.provider)
        _warn_experimental(account.provider)
        stored = store.get(account.provider, account.id)
        candidates = candidate_homes(
            paths,
            account,
            extra_homes=extra_homes,
            include_known=not extra_homes,
        )
        plan = plan_sync(account, stored, adapter, candidates)
        for problem in plan.problems:
            click.echo(f"warning: {problem}", err=True)
            problems += 1
        for note in plan.notes:
            click.echo(f"note: {note}", err=True)
        if plan.state == "missing-store-blob":
            click.echo(
                f"skipped {account.ref}: credential blob missing; run lairen update or register"
            )
            problems += 1
            continue
        if plan.state == "no-known-homes":
            click.echo(f"no known homes for {account.ref}")
            continue
        if plan.state == "update":
            old = epoch_to_iso(plan.old_access_expires_at) or "unknown"
            new = epoch_to_iso(plan.new_access_expires_at) or "unknown"
            if dry_run:
                click.echo(f"would update {account.ref} from {plan.home}: access {old} -> {new}")
                pending += 1
            else:
                apply_sync(paths, store, plan)
                click.echo(f"updated {account.ref} from {plan.home}: access {old} -> {new}")
            continue
        click.echo(f"current {account.ref}")

    if strict and (problems or pending):
        raise LairenError(f"strict sync failed: {problems + pending} issue(s) remain")


@cli.command(name="usage")
@click.argument("refs", nargs=-1)
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def usage(refs: tuple[str, ...], json_output: bool) -> None:
    """Show expiry and usage statistics (alias: stats)."""
    _, registry, store = _context()
    accounts = [registry.resolve(ref) for ref in refs] if refs else registry.list()
    if not accounts:
        click.echo("no accounts; run `lairen register <provider> --home <path>`")
        return

    records: list[dict[str, Any]] = []
    for account in accounts:
        record: dict[str, Any] = {
            "ref": account.ref,
            "provider": account.provider,
            "alias": account.alias,
            "label": account.label,
            "last_deployed_at": account.last_deployed_at,
        }
        blob = store.get(account.provider, account.id)
        if blob is None:
            record["error"] = "credential blob missing"
            records.append(record)
            continue
        usage_data = get_provider(account.provider).local_usage(blob)
        expires_at = usage_data.get("access_token_expires_at")
        remaining: int | None = None
        if isinstance(expires_at, (int, float)):
            remaining = int(float(expires_at) - time.time())
        record.update(
            {
                "expires_at": epoch_to_iso(expires_at),
                "expires_in_seconds": remaining,
                "expires_in": format_remaining(remaining),
                "usage": usage_data,
            }
        )
        records.append(record)

    if json_output:
        click.echo(json.dumps(records, indent=2))
        return

    rows = [
        (
            record["ref"],
            record.get("expires_at") or "-",
            record.get("expires_in") or "-",
            record.get("last_deployed_at") or "-",
        )
        for record in records
    ]
    _print_table(("REF", "ACCESS EXPIRES (UTC)", "REMAINING", "LAST DEPLOYED"), rows)


cli.add_command(usage, "stats")


@cli.command()
@click.argument("ref")
@click.option("--yes", is_flag=True, help="confirm removal")
def remove(ref: str, yes: bool) -> None:
    """Remove a saved account from the registry and credential store."""
    if not yes:
        raise LairenError("refusing to remove without --yes")
    paths, registry, store = _context()
    account = registry.resolve(ref)
    store.delete(account.provider, account.id)
    registry.remove(account.provider, account.id)
    _record_deployment(paths, "remove", account, source_home=account.source_home)
    click.echo(f"removed {account.ref}")


@cli.command()
@click.argument("ref", required=False)
@click.argument("name", required=False)
@click.option("--clear", "clear_alias", is_flag=True, help="remove the alias from REF")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def alias(
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
            {"ref": account.ref, "alias": account.alias}
            for account in registry.list()
            if account.alias
        ]
        if json_output:
            click.echo(json.dumps(aliases, indent=2))
            return
        if not aliases:
            click.echo("no aliases; run `lairen alias <ref> <name>`")
            return
        _print_table(
            ("ALIAS", "REF"),
            [(item["alias"], item["ref"]) for item in aliases],
        )
        return

    account = registry.resolve(ref)
    if clear_alias:
        if name:
            raise LairenError("cannot combine a name with --clear")
        if not account.alias:
            raise LairenError(f"{account.ref} has no alias")
        registry.clear_alias(account.provider, account.id)
        click.echo(f"cleared alias for {account.ref}")
        return
    if name is None:
        if json_output:
            click.echo(json.dumps({"ref": account.ref, "alias": account.alias}, indent=2))
        elif account.alias:
            click.echo(account.alias)
        else:
            click.echo(f"{account.ref} has no alias")
        return
    updated = registry.set_alias(account.provider, account.id, name)
    click.echo(f"aliased {updated.ref} -> {updated.alias}")


@cli.command()
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
@click.option("--register", "do_register", is_flag=True, help="save discovered accounts")
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def scan(
    directory: Path,
    depth: int,
    provider_filter: tuple[str, ...],
    do_register: bool,
    json_output: bool,
) -> None:
    """Scan a directory tree for Codex and Kimi credential homes."""
    providers = provider_filter or ("codex", "kimi")
    hits = scan_accounts(directory, depth=depth, providers=providers)
    if not hits:
        click.echo(f"no accounts found under {directory} (depth={depth})")
        return

    if do_register:
        _, registry, store = _context()
        for hit in best_per_account(hits):
            blob = hit.credential.read_text(encoding="utf-8")
            account = Account(
                provider=hit.provider,
                id=hit.identity.id,
                label=hit.identity.label,
                source_home=str(hit.home),
                extra=hit.identity.extra,
            )
            store.set(account.provider, account.id, blob)
            registry.upsert(account)
            click.echo(f"registered {account.ref}  source={hit.home}")
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


@cli.command()
def providers() -> None:
    """Show provider defaults and adapter status."""
    rows = [
        (
            adapter.name,
            "yes" if adapter.tested else "no",
            adapter.env_var or "-",
            str(adapter.default_home()),
            str(adapter.CREDENTIAL_RELPATH),
            adapter.deploy_note or "-",
        )
        for adapter in PROVIDERS.values()
    ]
    _print_table(
        ("PROVIDER", "TESTED", "ENV", "DEFAULT HOME", "CREDENTIAL", "NOTES"),
        rows,
    )


@cli.command()
def doctor() -> None:
    """Show resolved paths, account counts, and provider homes."""
    paths = Paths.resolve()
    registry = Registry(paths.registry_path)
    store = CredentialStore(paths.credentials_path)
    click.echo(f"config dir : {paths.config_dir}")
    click.echo(f"data dir   : {paths.data_dir}")
    click.echo(f"state dir  : {paths.state_dir}")
    click.echo(f"accounts   : {len(registry.load())}")
    click.echo(f"credentials: {store.count()}")
    for adapter in PROVIDERS.values():
        home = adapter.resolve_home()
        login = adapter.credential_path_for(home).is_file()
        tested = "yes" if adapter.tested else "no"
        click.echo(f"[{adapter.name}] tested={tested} home={home} login={'yes' if login else 'no'}")


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
    help="exit 1 when a project credential is unregistered, invalid, or drifted",
)
def status(
    directory: Path | None,
    provider_filter: tuple[str, ...],
    json_output: bool,
    strict: bool,
) -> None:
    """Show which accounts a project directory is using."""
    paths = Paths.resolve()
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
    if strict and not report.ok:
        raise LairenError(f"strict status failed: {len(report.problems)} problem account(s)")


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
    """Purpose, mental model, and the five core commands."""
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
