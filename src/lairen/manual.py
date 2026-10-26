"""Agent-oriented manual content.

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
    headers = ("provider", "tested", "credential", "home (env fallback)")
    rows = [
        (
            name,
            "yes" if adapter.tested else "no",
            str(adapter.CREDENTIAL_RELPATH),
            f"{_display_home(adapter.default_home())} ({adapter.env_var or '-'})",
        )
        for name, adapter in sorted(PROVIDERS.items())
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [
            max(width, len(cell)) for width, cell in zip(widths, row, strict=True)
        ]
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
lairen - store CLI-agent credentials and deploy them into target homes.

MODEL
  live provider home --register--> registry + credential store
  ref + --home PATH --deploy-----> target provider home

  A ref is provider/id:
    codex/alice@example.com
    kimi/user-123--device-456

  An account can carry a short alias:
    lairen alias kimi/user-123--device-456 kimi-a
    lairen deploy kimi-a --home ~/code/project/.kimi-code

CORE COMMANDS
  lairen scan ~/code --depth 2
  lairen register codex --home ~/code/project-a/.codex
  lairen list --json
  lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
  lairen update codex/alice@example.com --home ~/code/project-a/.codex
  lairen status ~/code/project-a
  lairen usage --json

RULES
  - deploy always needs --home. It is the provider home directory, not the
    credential file.
  - register resolves --home, then the provider env var, then the default home.
  - lairen never prints access tokens, refresh tokens, or API keys.
  - Stop the old agent before starting the new one. Two active homes sharing one
    OAuth session can invalidate each other.

NEXT
  lairen manual commands     command synopses and examples
  lairen manual workflows    task sequences
  lairen manual all          complete manual
  docs: https://igamenovoer.github.io/lairen/
"""

_COMMANDS = f"""\
Refs are provider/id, a unique alias, a bare id, or a label when unique.

register - save the live login from a provider home
  usage: lairen register PROVIDER [--home PATH] [--label TEXT] [--alias TEXT]
  providers: {", ".join(sorted(PROVIDERS))}
  examples:
    lairen register codex --home ~/code/project-a/.codex
    lairen register kimi --home ~/kimi-homes/kimi-1 --label lease-1 --alias kimi-1
  note: re-registration replaces the blob but preserves an existing alias.

list - list saved accounts
  usage: lairen list [--json]
  examples:
    lairen list
    lairen list --json
  columns: REF, ALIAS, LABEL, SOURCE, LAST DEPLOYED

status - show which accounts a project directory is using
  usage: lairen status [DIRECTORY] [--provider codex|kimi] [--json] [--strict]
  examples:
    lairen status
    lairen status ~/code/project-a --json
    lairen status ~/code/project-a --strict
  note: reads .codex and .kimi-code; leases come from the log and are checked.

show - show one account and its local usage metadata
  usage: lairen show REF
  example:
    lairen show codex/alice@example.com
  output: JSON object with "account" and "usage" keys

deploy - write a saved credential into a target home
  usage: lairen deploy REF --home PATH [--no-backup]
  examples:
    lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
    lairen deploy kimi/user-1--device-1 --home /tmp/work/.kimi-code --no-backup
  note: an existing target is snapshotted unless --no-backup is given.

update - replace a saved credential from a new provider home
  usage: lairen update REF --home PATH [--label TEXT]
  examples:
    lairen update kimi-2064-1 --home ~/kimi-homes/kimi-2064-1
    lairen update codex/alice@example.com --home ~/code/project-a/.codex
  note: alias and custom label survive; a changed identity changes the ref.

scan - discover Codex and Kimi credential homes
  usage: lairen scan DIRECTORY [--depth N] [--provider codex|kimi] [--register] [--json]
  examples:
    lairen scan ~/code --depth 2
    lairen scan ~/kimi-homes --provider kimi --register
  note: depth 0 = root only; depth 1 = root + immediate children (default).

usage - expiry and usage statistics
  usage: lairen usage [REF ...] [--json]   (alias: stats)
  examples:
    lairen usage
    lairen usage codex/alice@example.com --json

remove - delete an account and its stored credential
  usage: lairen remove REF --yes
  example:
    lairen remove codex/alice@example.com --yes
  note: deployed homes and snapshots are not touched.

alias - set, clear, or list stable account handles
  usage: lairen alias [REF] [NAME] [--clear] [--json]
  examples:
    lairen alias kimi/user-1--device-1 kimi-1
    lairen alias kimi-1
    lairen alias --json
    lairen alias kimi-1 --clear
  note: aliases are unique and resolve before ids and labels.

providers - list adapters, homes, and tested status
  usage: lairen providers

doctor - show resolved paths, counts, and login status
  usage: lairen doctor

manual - agent-oriented manual
  usage: lairen manual [TOPIC]
  examples:
    lairen manual
    lairen manual workflows
    lairen manual all --json
"""

_WORKFLOWS = """\
1. Discover every login under a tree
   lairen scan ~/code --depth 2
   lairen scan ~/code --depth 2 --register
   # --register keeps the newest copy per provider+id and ignores --json.

2. Save one specific login
   lairen register codex --home ~/code/project-a/.codex
   lairen list

3. Move an account to another project
   lairen register codex --home ~/code/project-a/.codex
   lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
   # Stop the agent in project-a first. deploy copies; it does not move.

4. Swap two registered accounts between projects
   lairen register codex --home ~/code/project-a/.codex
   lairen register codex --home ~/code/project-b/.codex
   lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
   lairen deploy codex/bob@example.com --home ~/code/project-a/.codex

5. Pick a Kimi session
   lairen usage --json
   lairen deploy kimi/user-1--device-2 --home ~/code/project-c/.kimi-code

6. Use a disposable home
   lairen deploy codex/alice@example.com --home /tmp/task-42/.codex --no-backup

7. Check what is about to expire
   lairen usage
   lairen usage --json
   # Re-register from the live home to capture refreshed tokens.

8. Remove a stale account
   lairen remove kimi/user-1--device-2 --yes

9. Alias long Kimi refs
   lairen alias 'kimi/dalvfss95eb18ppo13d0--23702bf7-c85b-4787-8e76-24a6e198653e' kimi-default
   lairen deploy kimi-default --home ~/code/project/.kimi-code

10. Repair a retired login in one line
    lairen update kimi-2064-1 --home ~/kimi-homes/kimi-2064-1
    # The alias survives; a changed device id changes the ref.

11. Check what a project is using
    cd ~/code/project-a
    lairen status
    lairen status ~/code/project-b --json
    # --strict exits 1 for unregistered, invalid, or drifted credentials.
"""

_PROVIDERS = f"""\
tested=yes means live-credential coverage.

{_provider_table()}

IDENTITIES
{_identity_table()}

REGISTER HOME ORDER
  --home > provider env var > default home

DEPLOY
  --home is required. Provider env vars never select a deploy target.

SCAN
  Only codex and kimi are auto-discovered.

EXPERIMENTAL
  claude, commandcode, cursor, and opencode print a warning and have no live
  tests. cursor needs an existing state.vscdb and must be closed during deploy.

Live data from the installed version:
  lairen providers
"""

_STORAGE = """\
DEFAULT PATHS
  config  ${XDG_CONFIG_HOME:-~/.config}/lairen/registry.json
  data    ${XDG_DATA_HOME:-~/.local/share}/lairen/credentials.json  (0600)
  state   <data>/state/snapshots/<provider>-<UTC timestamp>/<relpath>
          <data>/state/deployments.jsonl  (append-only deploy history)

LAIREN_HOME
  LAIREN_HOME=/abs/root -> /abs/root/{config,data,state}
  It changes storage only; it never selects a provider home.

REGISTRY
  JSON list of provider, id, label, source_home, created_at,
  last_deployed_at, last_deployed_home, and non-secret extra metadata.

CREDENTIAL STORE
  JSON object keyed "provider:id". Values are credential text: raw for codex
  and kimi, wrapped for the other adapters. Plaintext, mode 0600, atomic writes.

SNAPSHOTS
  A copy of an existing target is made before deploy replaces it. Snapshots are
  never pruned automatically and are not encrypted. Skip with --no-backup.
  Restore: cp <snapshot> <target credential>; chmod 600 <target credential>.

DEPLOYMENTS
  deployments.jsonl is append-only and records deploy, update, and remove
  events. status uses deploy entries to report other projects. No token
  material is written.

EXAMPLE
  LAIREN_HOME=/tmp/lairen-sandbox lairen register codex --home ~/code/p/.codex
  lairen doctor
"""

_JSON = """\
COMMANDS WITH JSON
  lairen list --json          list of accounts
  lairen usage --json         list of usage records
  lairen show REF             {account, usage}
  lairen scan DIR --json      list of scan hits
  lairen status DIR --json    {project, ok, accounts, warnings}
  lairen manual all --json    {version, topics: [{topic, title, text}]}

LIST RECORD
  {"ref", "provider", "id", "label", "source_home", "alias", "created_at",
   "last_deployed_at", "last_deployed_home", "extra"}

USAGE RECORD
  {"ref", "provider", "alias", "label", "last_deployed_at", "expires_at",
   "expires_in_seconds", "expires_in", "usage": {...}}
  A missing blob produces {"ref", ..., "error": "credential blob missing"}.

ALIAS JSON
  lairen alias --json        [{"ref", "alias"}]
  lairen alias REF --json    {"ref", "alias"}

SCAN HIT
  {"provider", "ref", "label", "home", "credential", "depth"}

STATUS RECORD
  {"provider", "ref", "alias", "label", "home", "credential", "state",
   "expires_at", "expires_in_seconds", "registry_expires_at",
   "registry_expires_in_seconds",
   "leases": [{"project", "home", "deployed_at", "legacy", "live"}], "error"}

TOPIC RECORD
  {"topic", "title", "text"}

NOTES
  scan --register ignores --json.
  expires_in_seconds is negative after expiry; expiry fields are null when
  no expiry claim is present.
  Exit codes: 0 success, 1 lairen error, 2 Click usage error.
"""

_SAFETY = """\
- lairen never prints access tokens, refresh tokens, or API keys.
- Registry and store are plaintext: directories 0700, files 0600. No encryption.
- deploy snapshots an existing target before replacement. Snapshots are
  plaintext too.
- Deployment copies credentials. Stop the old agent before starting the new one.
- OAuth refresh tokens rotate. Two active homes on one session can invalidate
  each other. Keep one active home per saved session.
- The stored blob does not follow refreshes. Re-register from the live home to
  capture a refreshed token.
- Experimental adapters: claude, commandcode, cursor, opencode.
- Never commit credentials.json, registry.json, or provider homes.
- remove --yes deletes the registry record and stored blob. Deployed homes and
  snapshots remain.

EXAMPLE
  # capture rotated tokens from the live home after an agent refreshes
  lairen register codex --home ~/code/project-b/.codex
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
