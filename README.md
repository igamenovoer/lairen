# lairen 来人

**Bring the right CLI-agent identity to the right place.**

[![PyPI](https://img.shields.io/pypi/v/lairen.svg)](https://pypi.org/project/lairen/)
[![Docs](https://img.shields.io/badge/docs-igamenovoer.github.io%2Flairen-blue)](https://igamenovoer.github.io/lairen/)
[![CI](https://github.com/igamenovoer/lairen/actions/workflows/ci.yml/badge.svg)](https://github.com/igamenovoer/lairen/actions/workflows/ci.yml)

Full documentation: <https://igamenovoer.github.io/lairen/>

`lairen` manages CLI-agent accounts for coding tools. An account is one
credential identity accepted by a provider CLI. It can keep a credential copy
inside lairen, point at one live holder home, or both. A project can use the
account by copying the stored auth, linking to the holder, or activating the
holder in the current shell.

Status: `2.1.0`, Pixi-managed, Click-based. Codex and Kimi are the tested
adapters; the other provider adapters are implemented but remain experimental
because this project has no live credentials for them yet.

## Why

- Keep credentials out of project repos and out of a single global home.
- Treat an account as one thing: identity, stored auth, holder home, aliases,
  usage, and deployments.
- Deploy by copying auth, by symlinking a project home to the holder, or by
  exporting the holder in the current shell.
- Preserve session-level Kimi identity: `(user_id, device_id)`, not just
  `user_id`, so independent logins of one account stay addressable.
- Mark a holder possibly stale after a copy deploy without preventing its use.
- Inspect expiry and usage from one command, including machine-readable JSON.

## Requirements

- Python `>=3.11` (the Pixi environment pins the 3.11 line)
- Pixi for the managed development environment
- Click for the CLI

## Install

Recommended with [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install lairen
lairen --help
```

Run it once without installing:

```bash
uvx lairen --help
```

From a source checkout:

```bash
uv venv
uv pip install -e .
uv run lairen --help
```

For project development:

```bash
pixi install
pixi run lairen --help
pixi run test
```

## Model

```text
account = provider + identity
  codex  -> email / account_key
  kimi   -> user_id--device_id

account
  ├── auth    optional credential copy inside lairen
  ├── holder  optional live, pre-logged-in home (at most one)
  └── deployments
        copy  stored auth -> project home
        link  project home -> holder home
        env   current shell -> holder home
```

An account can have:

- **auth only**: a normal copy-based account.
- **holder only**: no secret stored in lairen; link/env use the live home.
- **auth + holder**: lairen can copy or point at the live home.
- **neither**: identity metadata only.

## Quick start

Codex and Kimi are the tested paths:

```bash
# Record a live Codex home. Stores auth and makes it the holder.
lairen account add --provider codex --home ~/codex-holders/codex-aj --alias aj

# Record a Kimi home without storing a credential copy.
lairen account add --provider kimi --home ~/kimi-homes/kimi-2064-1 \
  --alias kimi-2064-1 --holder-only

# Account overview: auth, holder state, deployments.
lairen account list
lairen account show aj --json

# Copy stored auth into a project home.
lairen deploy copy aj --project ~/code/my-project

# Symlink the project home to the holder instead of copying.
lairen deploy link aj --project ~/code/other-project

# Activate the holder in the current shell.
eval "$(lairen deploy env aj)"

# Pull tokens refreshed in a holder or deployed home back into the store.
lairen account sync aj
lairen account sync aj --home ~/codex-holders/codex-aj

# Show what a project is using.
lairen status ~/code/my-project
lairen status ~/code/my-project --strict
```

## Holder homes

A holder home is one live provider home that stays in place. It is stored on
the account, not in a separate registry:

```json
{
  "provider": "codex",
  "id": "alice@example.com",
  "alias": "aj",
  "auth": {
    "stored": true,
    "captured_at": "2026-11-12T04:00:00+00:00",
    "source_home": "/home/me/codex-holders/codex-aj"
  },
  "holder": {
    "home": "/home/me/codex-holders/codex-aj",
    "recorded_at": "2026-11-10T09:00:00+00:00",
    "verified_at": "2026-11-12T04:00:00+00:00",
    "stale": null
  }
}
```

Deployment modes:

- **copy** writes the stored credential into a target home. If the account has
  a holder and the target is not the holder, the holder is marked
  `possibly-stale`. The copy still succeeds.
- **link** creates `<project>/<provider native home>` as a symlink to the
  holder. Project sessions, caches, and refreshed tokens land in the holder.
- **env** prints one shell export so the current shell and its children use the
  holder: `eval "$(lairen deploy env aj)"`.

`deploy env` also has opt-in tmux integration using
[libtmux](https://github.com/tmux-python/libtmux):

- `--tmux` types the export into the current tmux pane's shell.
- `--tmux-session` sets the session environment inherited by new panes.
- `--tmux-global` sets the tmux server global environment.
- `--no-overwrite` refuses to replace a different session/global value.
- `--no-print` suppresses the normal export line.

```bash
lairen deploy env aj --tmux
lairen deploy env aj --tmux --tmux-session
lairen deploy env aj --tmux-session --no-overwrite
```

`--tmux` requires lairen to be the foreground process in a pane running a
recognized shell. It never types into a running agent. Session/global changes
show the old and new value when they overwrite.

Staleness is advisory. `link` and `env` keep working and print a warning.
`lairen status --strict` fails and explains the reason plus the repair command:

```text
strict status failed: 1 problem(s)
  codex/alice@example.com: holder /home/me/codex-holders/codex-aj is possibly stale
    (since 2026-11-12T04:20:00+00:00: deploy copy -> /home/me/code/project-b/.codex)
    fix: lairen account sync codex/alice@example.com --home /home/me/codex-holders/codex-aj
```

## Scanning

Discover Codex and Kimi credential homes under a directory:

```bash
lairen account scan ~/code --depth 2
lairen account scan ~/codex-holders --depth 1 --provider codex
lairen account scan ~/tmp/workspace --add
lairen account scan ~/code --depth 2 --json
```

Depth `0` checks only the given directory; depth `1` (the default) also checks
its immediate children. Symlink directories and common noise directories
(`.git`, `.pixi`, `node_modules`, caches, build outputs) are skipped.

Without `--add`, scan only reports findings. With `--add`, it creates accounts
with stored auth and a holder home. `--holder-only` records holders without
copying auth.

Known patterns:

- Codex: `<dir>/auth.json` and `<dir>/.codex/auth.json`.
- Kimi: `<dir>/credentials/*.json`, `<dir>/.kimi-code/credentials/*.json`, and
  `<dir>/.kimi/credentials/*.json`.

## Provider surface

| Provider | Tested | Env | Default home | Project home | Credential |
|---|---:|---|---|---|---|
| `claude` | no | `CLAUDE_CONFIG_DIR` | `~/.claude` | `.claude` | `.credentials.json` |
| `codex` | yes | `CODEX_HOME` | `~/.codex` | `.codex` | `auth.json` |
| `commandcode` | no | `COMMANDCODE_HOME` | `~/.commandcode` | `.commandcode` | `auth.json` |
| `cursor` | no | `CURSOR_HOME` | `~/.config/Cursor/User/globalStorage` | none | `state.vscdb` |
| `kimi` | yes | `KIMI_CODE_HOME` | `~/.kimi-code` | `.kimi-code` | `credentials/*.json` |
| `opencode` | no | `OPENCODE_HOME` | `~/.local/share/opencode` | `.opencode` | `auth.json` |

`account add` requires an explicit `--home`; it does not fall back to the
provider environment variable. `deploy copy` and `deploy link` use
`<project>/<provider project home>` when `--home` is omitted. Cursor has no
project home name and requires `--home`. `deploy env` prints the provider
environment variable pointing at the holder.

## Commands

Top level:

| Command | Purpose |
|---|---|
| `lairen account ...` | Account identity, stored auth, holder, aliases, usage, scan, remove |
| `lairen deploy ...` | copy, link, env, list, unlink |
| `lairen status [DIR]` | Project view with auth, holder, and deployment state |
| `lairen providers` | Provider defaults and adapter status |
| `lairen doctor` | Paths, counts, schema, stale holders |
| `lairen migrate` | Migrate state to schema v3 |
| `lairen manual` | Agent-oriented manual |

Account subcommands:

```text
lairen account add --provider P --home PATH
                   [--alias A] [--label L] [--holder-only | --no-holder]
lairen account list [--provider P ...] [--available] [--with-holder]
                    [--stale-holders] [--json]
lairen account show REF [--json]
lairen account update REF --home PATH [--label L] [--keep-home]
lairen account sync [REF ...] [--home PATH ...] [--holder-only]
                    [--dry-run] [--strict] [--json]
lairen account set-home REF --home PATH [--sync] [--json]
lairen account clear-home REF [--json]
lairen account alias [REF] [NAME] [--clear] [--json]
lairen account usage [REF ...] [--json]          (alias: account stats)
lairen account scan DIR [--depth N] [--provider P] [--add] [--holder-only] [--json]
lairen account remove REF --yes [--json]
```

Deploy subcommands:

```text
lairen deploy copy REF [--project P] [--home PATH] [--sync] [--force] [--no-backup]
lairen deploy link REF [--project P] [--home PATH] [--force]
lairen deploy env REF [--shell auto|sh|bash|zsh|fish|csh|tcsh|powershell|pwsh|nu]
                   [--tmux] [--tmux-session] [--tmux-global]
                   [--no-overwrite] [--no-print]
lairen deploy list [--account REF ...] [--project P ...] [--provider P ...]
                   [--mode copy|link ...] [--group-by account|project]
                   [--active-only] [--json]
lairen deploy unlink REF [--project P] [--home PATH] --yes [--json]
```

`<ref>` is `provider/id` (for example `codex/alice@example.com` or
`kimi/alice--<device-id>`). A unique alias, bare id, or label is also accepted;
aliases resolve before ids and labels.

Agents can load the complete usage guide in one call:

```bash
lairen manual all
lairen manual all --json
```

## Storage

```
~/.config/lairen/
  registry.json          # accounts: identity, auth metadata, holder, alias
~/.local/share/lairen/
  schema.json            # state schema version, current v3
  credentials.json       # credential blobs, mode 0600
  state/snapshots/       # pre-copy copies of overwritten target files
  state/migrations/      # pre-migration backups
  state/deployments.jsonl # deploy/link/sync/update/remove history
```

Set `LAIREN_HOME=/absolute/path` to keep config, data, and state under one
root. It changes storage only; it never selects a provider home.

Schema v3 is required. State from lairen 1.x must be migrated explicitly:

```bash
lairen migrate --dry-run
lairen migrate
```

Migration converts account records to the new `auth`/`holder` shape, moves
legacy `last_deployed_*` bookkeeping into the deployment log, and adds
`mode=copy` to existing deployments. It does **not** adopt old `source_home`
values as holders. It reports them so you can attach one explicitly:

```bash
lairen account set-home REF --home PATH
```

## Design

- **Account is the aggregate root.** Identity, stored auth, holder, aliases,
  usage, and deployments are all reachable through `lairen account`.
- **One holder per account.** The holder is a live home, not a credential copy.
- **Registry and credentials stay separate.** Metadata is readable; secrets
  live in one `0600` JSON file.
- **Deployment is atomic.** Copy targets are written through a temporary file
  and `os.replace`, with a pre-deploy snapshot when the target exists.
- **Project status reads live homes.** `status` matches the project's actual
  credentials against the registry and reports unregistered, drifted, missing,
  linked, and env-bound state. `--strict` also fails on stale holders.
- **Copy and link are explicit.** `deploy copy` marks a holder possibly stale;
  `deploy link` and `deploy env` use the holder directly.
- **Kimi identity is a session.** `user_id` plus `device_id`, joined as
  `user_id--device_id`, so multiple logins of one account remain distinct.
- **Usage is local-first.** `usage` reports token expiry and refresh timestamps
  from stored blobs. Remote quota endpoints can plug in later.

## Development

```bash
pixi run test        # core + aux unit/integration suites
pixi run test-core   # tests for src/lairen
pixi run test-aux    # tests for repository support files
pixi run lint
pixi run typecheck
pixi run docs-serve  # live documentation preview
pixi run docs-build  # strict documentation build
```

Codex and Kimi are the only adapters with live-credential tests. Other
adapters use fake payloads or remain untested until credentials are available.

## Project layout

- `src/lairen/`: importable package and Click CLI
- `tests/core/`: tests for distributed code (`unit`, `integration`, `manual`)
- `tests/aux/`: tests for repository support content
- `extern/`: tracked, orphan, and linked-worktree external material
- `context/`: plans, features, design, summaries, and archived context
- `docs/`: MkDocs Material documentation source, published to GitHub Pages
- `scripts/`: repository automation outside the installed package
- `skillset/`: project-specific agent skills

## Security

Credential files are stored in plaintext with `0600` permissions, matching the
native clients. Do not commit `credentials.json`, `registry.json`, or any
provider home. Rotating OAuth refresh tokens cannot be safely shared by two
active homes at once; prefer one active home per saved session. `link` and
`env` intentionally share one live holder across projects, so concurrent
agents still share that OAuth session.

## Limitations

- Remote quota queries and OAuth refresh/write-back are not implemented.
- `cursor` requires Cursor to be closed while the SQLite database is updated.
- `opencode` covers the Go API-key slot; Console account switching stays with
  the official CLI.
- `claude`, `commandcode`, `cursor`, and `opencode` are experimental until
  live-credential tests are added.
- `scan` skips symlinked directories and reports any directory with a matching
  credential file, including backup copies; `--add` keeps the newest copy.
- lairen 1.x commands are removed. See the 2.0.0 changelog for the mapping.

## License

MIT
