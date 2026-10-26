"""Click command-line interface."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from lairen import __version__
from lairen.errors import LairenError
from lairen.models import Account
from lairen.paths import Paths
from lairen.providers import PROVIDERS, get_provider
from lairen.store import CredentialStore, Registry
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


def _print_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    click.echo(
        "  ".join(
            header.ljust(width)
            for header, width in zip(headers, widths, strict=True)
        )
    )
    click.echo("  ".join("-" * width for width in widths))
    for row in rows:
        click.echo(
            "  ".join(
                str(cell).ljust(width)
                for cell, width in zip(row, widths, strict=True)
            )
        )


def _warn_experimental(provider_name: str) -> None:
    provider = get_provider(provider_name)
    if not provider.tested:
        click.echo(
            f"warning: the {provider.name} adapter is experimental "
            f"({provider.deploy_note or 'no live credentials in this project'})",
            err=True,
        )


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
def register(provider: str, home: Path | None, label: str | None) -> None:
    """Save the live login from a provider home."""
    adapter = get_provider(provider)
    _warn_experimental(provider)
    home_path = adapter.resolve_home(home)
    blob = adapter.read_live(home_path)
    identity = adapter.parse_identity(home_path, blob)
    account = Account(
        provider=adapter.name,
        id=identity.id,
        label=label or identity.label,
        source_home=str(home_path),
        extra=identity.extra,
    )
    _, registry, store = _context()
    store.set(adapter.name, account.id, blob)
    registry.upsert(account)
    click.echo(f"registered {account.ref}  label={account.label}  source={home_path}")


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
            account.label,
            account.source_home or "-",
            account.last_deployed_at or "-",
        )
        for account in accounts
    ]
    _print_table(("REF", "LABEL", "SOURCE", "LAST DEPLOYED"), rows)


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
def deploy(ref: str, home: Path, no_backup: bool) -> None:
    """Write a saved credential into a target home."""
    paths, registry, store = _context()
    account = registry.resolve(ref)
    _warn_experimental(account.provider)
    blob = store.get(account.provider, account.id)
    if blob is None:
        raise LairenError(f"credential blob missing for {account.ref}")
    adapter = get_provider(account.provider)
    target_home = adapter.resolve_home(home)
    target_path = adapter.credential_path_for(target_home)

    snapshot: Path | None = None
    if target_path.exists() and not no_backup:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = (
            paths.snapshots_dir
            / f"{account.provider}-{stamp}"
            / adapter.CREDENTIAL_RELPATH
        )
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, snapshot)
        os.chmod(snapshot, 0o600)

    written = adapter.deploy(target_home, blob)
    account.last_deployed_at = utc_now()
    account.last_deployed_home = str(target_home)
    registry.upsert(account)
    click.echo(f"deployed {account.ref} -> {written}")
    if snapshot is not None:
        click.echo(f"snapshot: {snapshot}")


@cli.command(name="usage")
@click.argument("refs", nargs=-1)
@click.option("--json", "json_output", is_flag=True, help="emit machine-readable JSON")
def usage(refs: tuple[str, ...], json_output: bool) -> None:
    """Show expiry and usage statistics (alias: stats)."""
    _, registry, store = _context()
    accounts = (
        [registry.resolve(ref) for ref in refs] if refs else registry.list()
    )
    if not accounts:
        click.echo("no accounts; run `lairen register <provider> --home <path>`")
        return

    records: list[dict[str, Any]] = []
    for account in accounts:
        record: dict[str, Any] = {
            "ref": account.ref,
            "provider": account.provider,
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
    _, registry, store = _context()
    account = registry.resolve(ref)
    store.delete(account.provider, account.id)
    registry.remove(account.provider, account.id)
    click.echo(f"removed {account.ref}")


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
        click.echo(
            f"[{adapter.name}] tested={tested} home={home} login={'yes' if login else 'no'}"
        )


def main() -> None:
    cli(prog_name="lairen")
