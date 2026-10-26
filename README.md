# lairen 来人

**Bring the right CLI-agent identity to the right place.**

[![PyPI](https://img.shields.io/pypi/v/lairen.svg)](https://pypi.org/project/lairen/)
[![Docs](https://img.shields.io/badge/docs-igamenovoer.github.io%2Flairen-blue)](https://igamenovoer.github.io/lairen/)
[![CI](https://github.com/igamenovoer/lairen/actions/workflows/ci.yml/badge.svg)](https://github.com/igamenovoer/lairen/actions/workflows/ci.yml)

Full documentation: <https://igamenovoer.github.io/lairen/>

`lairen` is a Python credential registry and deployer for CLI coding agents.
It stores a provider login once, then materializes it into any target home on
demand — project-local, holder directories, or throwaway worktrees.

Status: `0.1.1`, Pixi-managed, Click-based. Codex and Kimi are the tested
adapters; the other provider adapters are implemented but remain experimental
because this project has no live credentials for them yet. Remote quota
queries and OAuth refresh are the next milestones.

## Why

- Keep credentials out of project repos and out of a single global home.
- Deploy a saved login into an arbitrary provider home.
- Preserve session-level Kimi identity: `(user_id, device_id)`, not just
  `user_id`, so independent logins of one account stay addressable.
- Inspect expiry and usage from one command, including machine-readable JSON.
- Use explicit CLI arguments first; common provider environment variables are
  respected only as fallbacks.

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

Add it to an existing uv project:

```bash
uv add lairen
```

From a source checkout:

```bash
uv venv
uv pip install -e .
uv run lairen --help
```

For project development, use Pixi:

```bash
pixi install
pixi run lairen --help
pixi run test
```

## Quick start

Codex and Kimi are the tested paths:

```bash
# Register a Codex home (reads auth.json, never prints tokens)
lairen register codex --home ~/codex-holder/.codex

# Register a Kimi home (reads credentials/kimi-code.json)
lairen register kimi --home ~/kimi-homes/kimi-2064-1

# List saved identities
lairen list

# Deploy a saved login into a project-local home
lairen deploy codex/alice@example.com --home ./my-project/.codex

# Usage / expiry report (alias: stats)
lairen usage
lairen usage kimi/alice--device-id --json
```

## Scanning

Discover Codex and Kimi credential homes under a directory:

```bash
lairen scan ~/code --depth 2
lairen scan ~/kimi-homes --depth 1 --provider kimi
lairen scan ~/tmp/workspace --register
lairen scan ~/code --depth 2 --json
```

Depth `0` checks only the given directory; depth `1` (the default) also checks
its immediate children, so `~/code/project/.codex` is found at the top level.
Symlink directories and common noise directories (`.git`, `.pixi`,
`node_modules`, caches, build outputs) are skipped.

Known patterns:

- Codex: `<dir>/auth.json` and `<dir>/.codex/auth.json`, validated by Codex
  auth fields.
- Kimi: `<dir>/credentials/*.json`, `<dir>/.kimi-code/credentials/*.json`, and
  `<dir>/.kimi/credentials/*.json`, validated by Kimi token fields. This
  includes `kimi-code.json` and `kimi-code-env-*.json` names.

Without `--register`, `scan` only reports findings. With `--register`, it
saves each unique account and keeps the newest copy when the same account
appears in multiple homes. Backup copies are reported as findings too.

## Provider surface

`lairen` exposes every provider surface that `subswap` supports. Adapters
marked `tested=no` are implemented against the upstream storage layouts but
have not been exercised with live credentials here.

| Provider | Tested | Env fallback | Default home | Credential | Notes |
|---|---:|---|---|---|---|
| `claude` | no | `CLAUDE_CONFIG_DIR` | `~/.claude` | `.credentials.json` | Merges `oauthAccount` metadata on deploy |
| `codex` | yes | `CODEX_HOME` | `~/.codex` | `auth.json` | ChatGPT OAuth |
| `commandcode` | no | `COMMANDCODE_HOME` | `~/.commandcode` | `auth.json` | API-key auth |
| `cursor` | no | `CURSOR_HOME` | `~/.config/Cursor/User/globalStorage` | `state.vscdb` | Desktop SQLite; close Cursor before deploying |
| `kimi` | yes | `KIMI_CODE_HOME` | `~/.kimi-code` | `credentials/*.json` | Session identity `user_id--device_id` |
| `opencode` | no | `OPENCODE_HOME` | `~/.local/share/opencode` | `auth.json` | Go API-key slot; Console accounts use the official CLI |

Provider home resolution order:

1. `--home <path>`
2. the provider environment variable (`CODEX_HOME`, `KIMI_CODE_HOME`, ...)
3. the provider default

Deployment always requires an explicit `--home`; `lairen` does not infer a
target from an environment variable.

## Commands

| Command | Purpose |
|---|---|
| `lairen register <provider> [--home PATH] [--label NAME]` | Save the live login from a provider home |
| `lairen list [--json]` | List saved accounts |
| `lairen show <ref>` | Show one account and its local usage metadata |
| `lairen deploy <ref> --home PATH` | Write a saved credential into a target home |
| `lairen scan DIR [--depth N] [--provider P] [--register] [--json]` | Discover Codex/Kimi homes |
| `lairen usage [ref ...] [--json]` | Expiry/usage statistics (alias: `stats`) |
| `lairen remove <ref> --yes` | Remove an account from the registry and store |
| `lairen providers` | Show provider defaults, tested status, and notes |
| `lairen doctor` | Show resolved paths, account counts, and provider homes |
| `lairen manual [topic] [--json]` | Agent-oriented manual; `manual all` loads the full guide |

`<ref>` is `provider/id` (for example `codex/alice@example.com` or
`kimi/alice--<device-id>`). A bare id or label is accepted when it is unique.

Agents can load the complete usage guide in one call:

```bash
lairen manual all
lairen manual all --json
```

## Storage

```
~/.config/lairen/
  registry.json          # account metadata: provider, id, label, source
~/.local/share/lairen/
  credentials.json       # credential blobs, mode 0600
  state/snapshots/       # pre-deploy copies of overwritten target files
```

Set `LAIREN_HOME=/absolute/path` to keep config, data, and state under one
root. This is a development and testing override, not an input mechanism for
provider selection.

## Design

- **Registry and credentials stay separate.** Metadata is readable; secrets
  live in one `0600` JSON file.
- **Deployment is atomic.** Target files are written through a temporary file
  and `os.replace`, with a pre-deploy snapshot when the target already exists.
  Provider-specific adapters merge rather than replace where upstream expects
  it (OpenCode Go slot, Cursor `ItemTable`, Claude `oauthAccount`).
- **Kimi identity is a session.** `user_id` plus `device_id`, joined as
  `user_id--device_id`, so multiple logins of one account remain distinct.
- **Usage is local-first.** `lairen usage` reports token expiry and refresh
  timestamps from stored blobs. Remote quota endpoints plug in behind
  `Provider.local_usage()` later.

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
active homes at once; prefer one active home per saved session.

## Limitations

- Remote quota queries and OAuth refresh/write-back are not implemented.
- `cursor` requires Cursor to be closed while the SQLite database is updated.
- `opencode` covers the Go API-key slot; Console account switching stays with
  the official CLI.
- `claude`, `commandcode`, `cursor`, and `opencode` are experimental until
  live-credential tests are added.
- `scan` skips symlinked directories and reports any directory with a matching
  credential file, including backup copies; `--register` keeps the newest copy.

## License

MIT
