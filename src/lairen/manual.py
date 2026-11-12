"""Agent-oriented manual content for lairen 2.x.

Each topic is short, example-driven plain text. ``manual all`` concatenates
every topic so an agent can load the complete guide in one call, and every
topic plus ``all`` can emit structured JSON.
"""

from __future__ import annotations

from pathlib import Path

from lairen import __version__
from lairen.providers import PROVIDERS

TOPIC_ORDER = (
    "overview",
    "commands",
    "workflows",
    "providers",
    "storage",
    "json",
    "safety",
)

IDENTITY_NOTES = {
    "claude": "emailAddress from oauthAccount, else JWT email",
    "codex": "account_key, else id_token email, else account_id",
    "commandcode": "cc-<sha256 prefix of API key>",
    "cursor": "cached email, else auth_id",
    "kimi": "user_id--device_id (session identity)",
    "opencode": "go-<sha256 prefix of API key>",
}


def _display_home(home: Path) -> str:
    try:
        relative = home.relative_to(Path.home())
    except ValueError:
        return str(home)
    return "~" if str(relative) == "." else f"~/{relative}"


def _provider_table() -> str:
    headers = ("provider", "tested", "env", "project home", "credential")
    rows = [
        (
            name,
            "yes" if adapter.tested else "no",
            adapter.env_var or "-",
            adapter.PROJECT_HOME_NAME or "-",
            str(adapter.CREDENTIAL_RELPATH),
        )
        for name, adapter in sorted(PROVIDERS.items())
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row, strict=True)]
    lines = [
        "  ".join(header.ljust(width) for header, width in zip(headers, widths, strict=True)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in rows
    )
    return "\n".join(line.rstrip() for line in lines)


def _identity_table() -> str:
    return "\n".join(
        f"  {name:<12} {IDENTITY_NOTES.get(name, 'see lairen providers')}"
        for name in sorted(PROVIDERS)
    )


_OVERVIEW = """\
lairen - manage CLI-agent accounts and holder homes.

MODEL
  account = one credential identity accepted by a provider CLI
    codex  email / account_key
    kimi   user_id--device_id
  each account may have:
    stored auth   a credential copy inside lairen
    holder home   one live, pre-logged-in provider home
  an account can have one, both, or neither.

DEPLOY MODES
  copy  stored auth -> project home (marks the holder possibly stale)
  link  project home -> account holder home (symlink)
  env   current shell -> account holder home (export command)

  lairen deploy copy codex/alice@example.com --project ~/code/project-a
  lairen deploy link codex/alice@example.com --project ~/code/project-b
  eval "$(lairen deploy env codex/alice@example.com)"

ACCOUNT EXAMPLE
  lairen account add --provider codex \\
    --home ~/codex-holders/codex-aj --alias aj
  lairen account list
  lairen account show aj --json
  lairen status ~/code/project-a

RULES
  - An account has at most one holder home.
  - A copy deploy marks the holder possibly stale but never blocks it.
  - link and env keep using the holder directly and warn when it is stale.
  - status --strict fails on stale, missing, or logged-out holders and
    prints the reason plus the command that repairs it.
  - lairen never prints access tokens, refresh tokens, or API keys.

NEXT
  lairen manual commands     command synopses
  lairen manual workflows    task sequences
  lairen manual all          complete manual
  docs: https://igamenovoer.github.io/lairen/
"""

_COMMANDS = """\
ACCOUNT
  lairen account add --provider P --home PATH [--alias A] [--label L]
        [--holder-only | --no-holder]
    Create/refresh an account. Default stores auth and sets the holder.
  lairen account list [--provider P ...] [--available] [--with-holder]
        [--stale-holders] [--json]
  lairen account show REF [--json]
  lairen account update REF --home PATH [--label L] [--keep-home]
    Rebind identity; may change the ref. New home becomes the holder.
  lairen account sync [REF ...] [--home PATH ...] [--holder-only]
        [--dry-run] [--strict] [--json]
    Pull fresher auth into the store. Never changes the holder.
  lairen account set-home REF --home PATH [--sync] [--json]
    Attach/replace the holder; identity must match.
  lairen account clear-home REF [--json]
  lairen account alias [REF] [NAME] [--clear] [--json]
  lairen account usage [REF ...] [--json]          (alias: account stats)
  lairen account scan DIRECTORY [--depth N] [--provider P]
        [--add] [--holder-only] [--json]
  lairen account remove REF --yes [--json]

DEPLOY
  lairen deploy copy REF [--project P] [--home PATH] [--sync]
        [--force] [--no-backup]
  lairen deploy link REF [--project P] [--home PATH] [--force]
  lairen deploy env REF [--shell auto|sh|bash|zsh|fish|csh|tcsh|powershell|pwsh|nu]
        [--tmux] [--tmux-session] [--tmux-global]
        [--no-overwrite] [--no-print]
  lairen deploy list [--account REF ...] [--project P ...] [--provider P ...]
        [--mode copy|link ...] [--group-by account|project]
        [--active-only] [--json]
  lairen deploy unlink REF [--project P] [--home PATH] --yes [--json]

INSPECT AND MAINTAIN
  lairen status [DIRECTORY] [--provider codex|kimi ...] [--json] [--strict]
  lairen providers
  lairen doctor
  lairen migrate [--dry-run] [--project HOME=PROJECT ...] [--no-backup]
  lairen manual [TOPIC]

REFS
  provider/id, a unique alias, a bare id, or a unique label.
  Deploy copy resolves accounts. Deploy link/env and account subcommands
  resolve the same account registry; holders are part of the account.
"""

_WORKFLOWS = """\
1. Record an existing logged-in home
   lairen account add --provider codex \\
     --home ~/codex-holders/codex-aj --alias aj
   lairen account list

2. Record a holder only, with no credential copy in lairen
   lairen account add --provider codex \\
     --home ~/codex-holders/codex-temp --holder-only

3. Add stored auth to a holder-only account
   lairen account sync aj --home ~/codex-holders/codex-aj

4. Replace the holder after moving a home
   lairen account set-home aj --home ~/codex-holders/codex-aj-v2 --sync

5. Make a project use the holder directly
   lairen account set-home aj --home ~/codex-holders/codex-aj
   lairen deploy link aj --project ~/code/project-a
   lairen status ~/code/project-a

6. Use the holder only in the current shell
   eval "$(lairen deploy env aj)"
   lairen status
   # link copies no bytes; the project gets .codex -> holder home.

   Inside tmux:
   lairen deploy env aj --tmux
   lairen deploy env aj --tmux --tmux-session
   lairen deploy env aj --tmux-session --no-overwrite
   # --tmux types into the current pane; --tmux-session sets future panes.

7. Copy stored auth to another project
   lairen deploy copy aj --project ~/code/project-b
   # The holder is marked possibly stale. It still works; status warns.

8. Repair a stale holder
   lairen account sync aj --home ~/codex-holders/codex-aj
   lairen status ~/code/project-b --strict

9. Sync from a specific home
   lairen account sync aj --home ~/code/project-b/.codex --dry-run
   lairen account sync aj --home ~/code/project-b/.codex

10. Identity changed (new Kimi device)
    lairen account update aj --home ~/kimi-homes/kimi-2064-2
    # The ref changes; the alias survives; the new home becomes the holder.

11. Find accounts with no active deployment
    lairen account list --available

12. Find stale holders
    lairen account list --stale-holders

13. Review deployments
    lairen deploy list --group-by account
    lairen deploy list --group-by project --active-only

14. Remove a project link
    lairen deploy unlink aj --project ~/code/project-a --yes

15. Migrate from lairen 1.x
    lairen migrate --dry-run
    lairen migrate
    lairen account set-home REF --home PATH
    # 1.x source_home is reported, never adopted automatically.
"""

_PROVIDERS = f"""\
tested=yes means live-credential coverage.

{_provider_table()}

IDENTITIES
{_identity_table()}

ACCOUNT ADD
  --home is required. The provider env var is not used as an add fallback;
  it is used by deploy env and by doctor's default-home report.

DEPLOY
  copy writes the stored credential into the target.
  link symlinks <project>/<provider project home> -> holder home.
  env prints an export for the provider env var.
  cursor has no project home name; link requires --home.

STALENESS
  copy deploy to a home other than the holder marks the holder possibly
  stale. It is advisory: link and env still work. status --strict fails
  and prints the reason and fix.

EXPERIMENTAL
  claude, commandcode, cursor, and opencode have no live tests.
  cursor needs an existing state.vscdb and must be closed during copy.

Live data from the installed version:
  lairen providers
"""

_STORAGE = """\
DEFAULT PATHS
  config  ${XDG_CONFIG_HOME:-~/.config}/lairen/registry.json
  data    ${XDG_DATA_HOME:-~/.local/share}/lairen/credentials.json  (0600)
          <data>/schema.json  (state schema version, current v3)
  state   <data>/state/snapshots/<provider>-<UTC timestamp>/<relpath>
          <data>/state/migrations/<UTC timestamp>/  (pre-migration backups)
          <data>/state/deployments.jsonl  (append-only history)

LAIREN_HOME
  LAIREN_HOME=/abs/root -> /abs/root/{config,data,state}
  It changes storage only; it never selects a provider home.

SCHEMA
  schema.json records the state version. State without it is legacy.
  lairen 2.x uses v3 and requires migration from v1/v2:
    lairen migrate
  Commands refuse older state until it is migrated. doctor reports it.

REGISTRY
  JSON list of accounts:
    provider, id, label, alias, created_at, extra
    auth:   {{stored, captured_at, source_home}}
    holder: {{home, recorded_at, verified_at, stale}}
  stale is null or {{since, reason}}.
  No token material. One holder per account.

CREDENTIAL STORE
  JSON object keyed "provider:id". Values are credential text: raw for
  codex and kimi, wrapped for other adapters. Plaintext, mode 0600.

SNAPSHOTS
  A copy of an existing target is made before copy deploy replaces it.
  Snapshots are never pruned and are not encrypted. Skip with --no-backup.
  Restore: cp <snapshot> <target credential>; chmod 600 <target credential>.

DEPLOYMENTS
  deployments.jsonl records deploy, link, sync, update, remove, set-home,
  clear-home, and unlink events. Every deployment entry has a mode:
  copy or link. status uses deploy/link entries for other projects.

EXAMPLE
  LAIREN_HOME=/tmp/lairen-sandbox lairen account add \\
    --provider codex --home ~/codex-holders/codex-aj
  lairen doctor
"""

_JSON = """\
COMMANDS WITH JSON
  lairen account list --json       list of full account payloads
  lairen account show REF --json   account + auth + holder + deployments
  lairen account usage --json      list of usage records
  lairen account sync --json       list of sync results
  lairen account scan DIR --json   list of scan hits
  lairen deploy list --json        list of deployment records
  lairen deploy unlink REF --json  removed link details
  lairen status DIR --json         {project, ok, accounts, shell, problems}
  lairen manual all --json         {version, topics: [{topic, title, text}]}

ACCOUNT PAYLOAD
  {"ref", "provider", "id", "label", "alias", "created_at", "extra",
   "auth": {"stored", "present", "captured_at", "source_home", "usage"?},
   "holder": {"home", "recorded_at", "verified_at", "stale", "live"?},
   "holder_state", "deployments": [...]}

DEPLOYMENT RECORD
  {"provider", "ref", "alias", "label", "project", "home",
   "deployed_at", "state", "mode", "source_home"}
  state is "active" or "overwritten"; mode is "copy" or "link".

USAGE RECORD
  {"ref", "provider", "alias", "label", "holder", "holder_state",
   "expires_at", "expires_in_seconds", "expires_in", "usage": {...}}
  A missing blob produces {"ref", ..., "error": "credential blob missing"}.

STATUS RECORD
  {"project", "ok",
   "accounts": [{"provider", "ref", "alias", "label", "home", "credential",
                 "source", "state", "expires_at", "expires_in_seconds",
                 "registry_expires_at", "registry_expires_in_seconds",
                 "leases": [{"project", "home", "deployed_at", "live", "mode"}],
                 "holder", "holder_state", "holder_reason", "link",
                 "link_mismatch", "error"}],
   "shell": [{"provider", "env_var", "home", "ref", "alias", "holder_state"}],
   "problems": [{"kind", "ref", "message", "fix"}],
   "warnings": ["..."]}

TOPIC RECORD
  {"topic", "title", "text"}

NOTES
  expires_in_seconds is negative after expiry; expiry fields are null when
  no expiry claim is present.
  Exit codes: 0 success, 1 lairen error, 2 Click usage error.
"""

_SAFETY = """\
- lairen never prints access tokens, refresh tokens, or API keys.
- Registry and store are plaintext: directories 0700, files 0600. No encryption.
- copy deploy snapshots an existing target before replacement. Snapshots are
  plaintext too.
- copy duplicates credentials. Stop the old agent before starting the new one.
- One holder per account. link and env share that live home across projects;
  concurrent agents still share one OAuth session.
- copy deploy to another project can rotate the session and make the holder
  stale. lairen marks it possibly stale; it does not block link/env use.
- status --strict fails on stale, missing, or logged-out holders. The error
  names the account, reason, and repair command.
- deploy env --tmux only types into the current pane when lairen is the
  foreground process and the waiting process is a recognized shell. It refuses
  to type into a running agent. --tmux-session and --tmux-global are the safe
  session-level alternatives.
- account sync reads the holder and known deployed homes; it never writes a
  provider home.
- account update changes the ref when identity changes. The alias survives.
- account remove --yes deletes the record and stored auth. Holder homes and
  project symlinks remain on disk.
- Experimental adapters: claude, commandcode, cursor, opencode.
- Never commit credentials.json, registry.json, or provider homes.

EXAMPLE
  # capture rotated tokens, then verify the project
  lairen account sync codex/alice@example.com \\
    --home ~/codex-holders/codex-aj
  lairen status ~/code/project-b --strict
"""

TOPICS: dict[str, tuple[str, str]] = {
    "overview": ("Overview", _OVERVIEW),
    "commands": ("Commands", _COMMANDS),
    "workflows": ("Workflows", _WORKFLOWS),
    "providers": ("Providers", _PROVIDERS),
    "storage": ("Storage", _STORAGE),
    "json": ("JSON output", _JSON),
    "safety": ("Safety", _SAFETY),
}


def topic_payload(slug: str) -> dict[str, str]:
    title, text = TOPICS[slug]
    return {"topic": slug, "title": title, "text": text}


def all_payload() -> dict[str, object]:
    return {
        "version": __version__,
        "topics": [topic_payload(slug) for slug in TOPIC_ORDER],
    }


def all_text() -> str:
    sections = [f"lairen manual - complete agent manual\nversion: {__version__}"]
    for slug in TOPIC_ORDER:
        title, text = TOPICS[slug]
        sections.append(f"{title.upper()}\n{'-' * len(title)}\n{text}")
    return "\n\n".join(sections)
