# lairen 来人

**Bring the right CLI-agent identity to the right place.**

`lairen` is a small Python credential registry and deployer for CLI coding
agents. It stores a provider login once, then materializes it into any target
home on demand — project-local, holder directories, or throwaway worktrees.

Status: early scaffold (`0.1.0`). Local registration, listing, deployment, and
usage metadata work today; remote quota queries and OAuth refresh are the next
milestones.

## Why

- Keep credentials out of project repos and out of a single global home.
- Deploy a saved login into an arbitrary `CODEX_HOME` or `KIMI_CODE_HOME`.
- Preserve session-level Kimi identity: `(user_id, device_id)`, not just
  `user_id`, so multiple logins of the same account stay distinct.
- Inspect expiry and usage from one command, including machine-readable JSON.
- Standard library only; no runtime dependencies.

## Install

```bash
python -m pip install -e .
lairen --help
```

## Quick start

```bash
# Register a Codex home (reads auth.json, never prints tokens)
lairen register codex --home ~/codex-holder/.codex

# Register a Kimi home (reads credentials/kimi-code.json)
lairen register kimi --home ~/kimi-homes/kimi-2064-1

# List saved identities
lairen list

# Deploy a saved login into a project-local home
lairen deploy codex/alice@example.com --home ./my-project/.codex

# Usage / expiry report (also available as `lairen stats`)
lairen usage
lairen usage kimi/alice--device-id --json
```

Provider homes resolve in this order:

1. `--home <path>`
2. provider environment variable (`CODEX_HOME`, `KIMI_CODE_HOME`)
3. provider default (`~/.codex`, `~/.kimi-code`)

## Storage

```
~/.config/lairen/
  registry.json          # account metadata: provider, id, label, source
~/.local/share/lairen/
  credentials.json       # credential blobs, mode 0600
  state/snapshots/       # pre-deploy copies of overwritten target files
```

Set `LAIREN_HOME=/absolute/path` to keep config, data, and state under one
root (useful for tests and per-session registries).

## Commands

| Command | Purpose |
|---|---|
| `lairen register <provider> [--home PATH] [--label NAME]` | Save the live login from a provider home |
| `lairen list [--json]` | List saved accounts |
| `lairen show <ref>` | Show one account and its local usage metadata |
| `lairen deploy <ref> --home PATH` | Write a saved credential into a target home |
| `lairen usage [ref ...] [--json]` | Expiry/usage statistics (alias: `stats`) |
| `lairen remove <ref> --yes` | Remove an account from the registry and store |
| `lairen providers` | Show provider defaults and credential paths |
| `lairen doctor` | Show resolved paths and provider homes |

`<ref>` is `provider/id` (for example `codex/alice@example.com` or
`kimi/alice--<device-id>`). A bare id is accepted when it is unique.

## Design

- **Registry and credentials are separate.** The registry holds metadata only;
  credential blobs live in a single `0600` JSON file.
- **Deployment is atomic.** Target files are written through a temporary file
  and `os.replace`, with a pre-deploy snapshot when the target already exists.
- **Kimi identity is a session.** `user_id` plus `device_id` from the access
  token JWT, joined as `user_id--device_id`. This keeps independent logins of
  the same account addressable.
- **Usage is local-first.** `lairen usage` reports token expiry and refresh
  timestamps from stored blobs. Remote quota endpoints plug in behind
  `Provider.local_usage()` later.

## Security

Credential files are stored in plaintext with `0600` permissions, matching the
native clients. Do not commit `credentials.json`, `registry.json`, or any
provider home. Rotating OAuth refresh tokens cannot be safely shared by two
active homes at once; prefer one active home per saved session.

## Roadmap

- Remote quota queries for Codex and Kimi
- OAuth refresh with lock-aware write-back
- Claude Code and Cursor providers
- Import from `subswap` and `kimi-project.py`
- Optional background daemon and auto-selection

## License

MIT
