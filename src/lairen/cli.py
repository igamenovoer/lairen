"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .errors import LairenError
from .models import Account
from .paths import Paths
from .providers import PROVIDERS, get_provider
from .store import CredentialStore, Registry
from .util import epoch_to_iso, format_remaining, utc_now


def _context() -> tuple[Paths, Registry, CredentialStore]:
    paths = Paths.resolve().ensure()
    return paths, Registry(paths.registry_path), CredentialStore(paths.credentials_path)


def _print_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)))


def cmd_register(args: argparse.Namespace) -> int:
    provider = get_provider(args.provider)
    home = provider.resolve_home(args.home)
    blob = provider.read_live(home)
    identity = provider.parse_identity(blob)
    account = Account(
        provider=provider.name,
        id=identity.id,
        label=args.label or identity.label,
        source_home=str(home),
        extra=identity.extra,
    )
    _, registry, store = _context()
    store.set(provider.name, account.id, blob)
    registry.upsert(account)
    print(f"registered {account.ref}  label={account.label}  source={home}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    _, registry, _ = _context()
    accounts = registry.list()
    if args.json:
        print(json.dumps([account.to_dict() for account in accounts], indent=2))
        return 0
    if not accounts:
        print("no accounts; run `lairen register <provider> --home <path>`")
        return 0
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
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    _, registry, store = _context()
    account = registry.resolve(args.ref)
    blob = store.get(account.provider, account.id)
    if blob is None:
        raise LairenError(f"credential blob missing for {account.ref}")
    provider = get_provider(account.provider)
    payload = {
        "account": account.to_dict(),
        "usage": provider.local_usage(blob),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    paths, registry, store = _context()
    account = registry.resolve(args.ref)
    blob = store.get(account.provider, account.id)
    if blob is None:
        raise LairenError(f"credential blob missing for {account.ref}")
    provider = get_provider(account.provider)
    target_home = provider.resolve_home(args.home)
    target_path = provider.credential_path_for(target_home)

    snapshot: Path | None = None
    if target_path.exists() and not args.no_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = paths.snapshots_dir / f"{account.provider}-{stamp}" / provider.credential_relpath
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, snapshot)
        os.chmod(snapshot, 0o600)

    written = provider.write_live(target_home, blob)
    account.last_deployed_at = utc_now()
    account.last_deployed_home = str(target_home)
    registry.upsert(account)
    print(f"deployed {account.ref} -> {written}")
    if snapshot is not None:
        print(f"snapshot: {snapshot}")
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    _, registry, store = _context()
    accounts = (
        [registry.resolve(ref) for ref in args.refs]
        if args.refs
        else registry.list()
    )
    if not accounts:
        print("no accounts; run `lairen register <provider> --home <path>`")
        return 0

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
        usage = get_provider(account.provider).local_usage(blob)
        expires_at = usage.get("access_token_expires_at")
        remaining: int | None = None
        if isinstance(expires_at, (int, float)):
            remaining = int(float(expires_at) - time.time())
        record.update(
            {
                "expires_at": epoch_to_iso(expires_at),
                "expires_in_seconds": remaining,
                "expires_in": format_remaining(remaining),
                "usage": usage,
            }
        )
        records.append(record)

    if args.json:
        print(json.dumps(records, indent=2))
        return 0

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
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    if not args.yes:
        raise LairenError("refusing to remove without --yes")
    _, registry, store = _context()
    account = registry.resolve(args.ref)
    store.delete(account.provider, account.id)
    registry.remove(account.provider, account.id)
    print(f"removed {account.ref}")
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    rows = [
        (provider.name, provider.env_var, str(provider.default_home), str(provider.credential_relpath))
        for provider in PROVIDERS.values()
    ]
    _print_table(("PROVIDER", "ENV", "DEFAULT HOME", "CREDENTIAL"), rows)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = Paths.resolve()
    registry = Registry(paths.registry_path)
    store = CredentialStore(paths.credentials_path)
    print(f"config dir : {paths.config_dir}")
    print(f"data dir   : {paths.data_dir}")
    print(f"state dir  : {paths.state_dir}")
    print(f"accounts   : {len(registry.load())}")
    print(f"credentials: {store.count()}")
    for provider in PROVIDERS.values():
        home = provider.resolve_home()
        login = provider.credential_path_for(home).is_file()
        print(
            f"[{provider.name}] home={home} login={'yes' if login else 'no'}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lairen",
        description="Store CLI-agent credentials and deploy them into target homes.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register", help="save the live login from a provider home")
    register.add_argument("provider", choices=sorted(PROVIDERS))
    register.add_argument("--home", help="provider home to read from")
    register.add_argument("--label", help="override the display label")
    register.set_defaults(func=cmd_register)

    listing = sub.add_parser("list", help="list saved accounts")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="show one account and its usage metadata")
    show.add_argument("ref")
    show.set_defaults(func=cmd_show)

    deploy = sub.add_parser("deploy", help="write a saved credential into a target home")
    deploy.add_argument("ref")
    deploy.add_argument("--home", required=True, help="target provider home")
    deploy.add_argument("--no-backup", action="store_true", help="skip the pre-deploy snapshot")
    deploy.set_defaults(func=cmd_deploy)

    usage = sub.add_parser(
        "usage", aliases=["stats"], help="show expiry and usage statistics"
    )
    usage.add_argument("refs", nargs="*")
    usage.add_argument("--json", action="store_true")
    usage.set_defaults(func=cmd_usage)

    remove = sub.add_parser("remove", help="remove a saved account")
    remove.add_argument("ref")
    remove.add_argument("--yes", action="store_true", help="confirm removal")
    remove.set_defaults(func=cmd_remove)

    providers = sub.add_parser("providers", help="show provider defaults")
    providers.set_defaults(func=cmd_providers)

    doctor = sub.add_parser("doctor", help="show resolved paths and provider homes")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except LairenError as exc:
        print(f"lairen: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"lairen: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
