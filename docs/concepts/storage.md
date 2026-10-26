# Storage and paths

lairen keeps metadata, credentials, and pre-deploy snapshots in three
directories. It follows the XDG base-directory convention and creates
directories with mode `0700` and files with mode `0600`.

## Default layout

| Purpose | Path |
|---|---|
| Config | `${XDG_CONFIG_HOME:-~/.config}/lairen/` |
| Registry | `${XDG_CONFIG_HOME:-~/.config}/lairen/registry.json` |
| Data | `${XDG_DATA_HOME:-~/.local/share}/lairen/` |
| Credential store | `${XDG_DATA_HOME:-~/.local/share}/lairen/credentials.json` |
| State | `~/.local/share/lairen/state/` |
| Snapshots | `~/.local/share/lairen/state/snapshots/` |
| Deployment log | `~/.local/share/lairen/state/deployments.jsonl` |

`lairen doctor` prints the paths that are actually in effect.

## Single-root override

Set `LAIREN_HOME` to keep everything under one root, which is useful for tests
and disposable environments:

```bash
LAIREN_HOME=/tmp/lairen-state lairen register codex --home ./project/.codex
```

The layout becomes:

```text
/tmp/lairen-state/
  config/registry.json
  data/credentials.json
  data/state/snapshots/
  data/state/deployments.jsonl
```

`LAIREN_HOME` is a storage override, not a provider selector. It does not
change which provider home `register` reads or where `deploy` writes.

## Registry format

`registry.json` is a JSON list of account records:

```json
[
  {
    "provider": "codex",
    "id": "alice@example.com",
    "label": "alice@example.com",
    "source_home": "/home/alice/code/project-a/.codex",
    "alias": "work",
    "created_at": "2026-10-26T12:00:00+00:00",
    "last_deployed_at": "2026-10-26T12:05:00+00:00",
    "last_deployed_home": "/home/alice/code/project-b/.codex",
    "extra": {
      "email": "alice@example.com",
      "account_id": "acct_123",
      "name": "Alice"
    }
  }
]
```

`alias` is optional and holds the user-chosen short handle. `extra` is
provider-specific and never contains access or refresh tokens. It can contain
an email address, account identifiers, or a device id, so treat the registry as
private even though it holds no secrets.

Writes go through a temporary file, `fsync`, and `os.replace`, so a crash does
not leave a half-written registry.

## Credential store format

`credentials.json` is a JSON object mapping `provider:id` to the raw saved
credential blob:

```json
{
  "codex:alice@example.com": "{\n  \"tokens\": { ... }\n}\n",
  "kimi:u_123--d_456": "{\n  \"access_token\": \"...\"\n}\n"
}
```

The value is stored as text:

- `codex`: the contents of `auth.json`, unchanged.
- `kimi`: the contents of the selected `credentials/*.json`, unchanged.
- `claude`: a JSON wrapper containing `credentials` and `oauth_account`.
- `commandcode` and `opencode`: a small JSON wrapper containing the API key.
- `cursor`: a normalized JSON object extracted from the SQLite database.

The whole file is written atomically with mode `0600`. When `lairen update`
rebinds an account whose identity changed, it writes the blob under the new
`provider:id` key and removes the old key.

## Snapshots

Before `deploy` overwrites an existing target credential, it copies the target
to:

```text
<state>/snapshots/<provider>-<UTC timestamp>/<credential relpath>
```

For example:

```text
~/.local/share/lairen/state/snapshots/codex-20261026T120000000000Z/auth.json
```

Snapshots are ordinary files with mode `0600`. They are never pruned
automatically; delete old timestamp directories when you no longer need them.
Use `--no-backup` to skip snapshot creation for a deployment.

## Deployment log

`<state>/deployments.jsonl` is an append-only JSON Lines history written by
`deploy`, `update`, and `remove`. It records the account, alias, target home,
source home, and timestamp. No token material is written.

```json
{
  "ts": "2026-10-26T12:00:00+00:00",
  "action": "deploy",
  "provider": "codex",
  "ref": "codex/alice@example.com",
  "alias": "work",
  "project": "/home/me/code/project-b",
  "home": "/home/me/code/project-b/.codex",
  "source_home": "/home/me/code/project-a/.codex"
}
```

`lairen status` uses deploy entries to report which other projects hold an
account, checking each target's current credential and marking overwritten
targets. History starts when this log is first written; older accounts fall
back to the single `last_deployed_home` registry field and are marked as a
legacy last deploy.

## Provider home resolution

For `register`, a provider home is resolved in this order:

1. `--home PATH`
2. the provider's environment variable, such as `CODEX_HOME` or
   `KIMI_CODE_HOME`
3. the provider's default home

For `deploy`, `--home` is required. lairen never reads an environment variable
to choose a deployment target.

| Provider | Environment variable | Default home |
|---|---|---|
| `claude` | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| `codex` | `CODEX_HOME` | `~/.codex` |
| `commandcode` | `COMMANDCODE_HOME` | `~/.commandcode` |
| `cursor` | `CURSOR_HOME` | `${XDG_CONFIG_HOME:-~/.config}/Cursor/User/globalStorage` |
| `kimi` | `KIMI_CODE_HOME` | `~/.kimi-code` |
| `opencode` | `OPENCODE_HOME` | `${XDG_DATA_HOME:-~/.local/share}/opencode` |

`--home` is the provider home directory itself, not the credential file. For
Codex, pass `~/.codex`, not `~/.codex/auth.json`. For Kimi, pass
`~/.kimi-code`, not its `credentials/` subdirectory.

## What lairen does not store

- It does not copy whole provider homes, only the credential file.
- It does not write to the source home during `register`.
- It does not refresh or rewrite tokens in the store after deployment.
- It does not encrypt the credential store. See the
  [security model](security.md).
