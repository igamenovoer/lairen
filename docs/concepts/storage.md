# Storage and paths

lairen keeps account metadata, credential blobs, and pre-deploy snapshots in
three directories. It follows the XDG base-directory convention and creates
directories with mode `0700` and files with mode `0600`.

## Default layout

| Purpose | Path |
|---|---|
| Config | `${XDG_CONFIG_HOME:-~/.config}/lairen/` |
| Registry | `${XDG_CONFIG_HOME:-~/.config}/lairen/registry.json` |
| Data | `${XDG_DATA_HOME:-~/.local/share}/lairen/` |
| Schema marker | `${XDG_DATA_HOME:-~/.local/share}/lairen/schema.json` |
| Credential store | `${XDG_DATA_HOME:-~/.local/share}/lairen/credentials.json` |
| State | `~/.local/share/lairen/state/` |
| Snapshots | `~/.local/share/lairen/state/snapshots/` |
| Migration backups | `~/.local/share/lairen/state/migrations/` |
| Deployment log | `~/.local/share/lairen/state/deployments.jsonl` |

`lairen doctor` prints the paths that are actually in effect.

## Single-root override

Set `LAIREN_HOME` to keep everything under one root, which is useful for tests
and disposable environments:

```bash
LAIREN_HOME=/tmp/lairen-state lairen account add \
  --provider codex --home ./project/.codex
```

The layout becomes:

```text
/tmp/lairen-state/
  config/registry.json
  data/credentials.json
  data/schema.json
  data/state/snapshots/
  data/state/migrations/
  data/state/deployments.jsonl
```

`LAIREN_HOME` is a storage override, not a provider selector. It does not
change which provider home `account add` reads or where `deploy copy` writes.

## Schema version

`schema.json` records the on-disk state version. lairen 2.x uses **v3**.

```json
{"version": 3}
```

State without a marker is legacy. State at v1 or v2 must be migrated:

```bash
lairen migrate --dry-run
lairen migrate
```

Commands refuse older state with a `lairen migrate` hint. `doctor` reports the
schema without failing so it can be used to diagnose old state.

## Registry format

`registry.json` is a JSON list of account records. The account is the aggregate
root: identity, auth metadata, and at most one holder.

```json
[
  {
    "provider": "codex",
    "id": "alice@example.com",
    "label": "alice@example.com",
    "alias": "aj",
    "created_at": "2026-11-10T09:00:00+00:00",
    "auth": {
      "stored": true,
      "captured_at": "2026-11-12T04:00:00+00:00",
      "source_home": "/home/alice/codex-holders/codex-aj"
    },
    "holder": {
      "home": "/home/alice/codex-holders/codex-aj",
      "recorded_at": "2026-11-10T09:00:00+00:00",
      "verified_at": "2026-11-12T04:00:00+00:00",
      "stale": {
        "since": "2026-11-12T04:20:00+00:00",
        "reason": "deploy copy -> /home/alice/code/project-b/.codex"
      }
    },
    "extra": {
      "email": "alice@example.com",
      "account_id": "acct_123",
      "name": "Alice"
    }
  }
]
```

Fields:

| Field | Meaning |
|---|---|
| `auth` | Metadata for the credential copy. `null` when absent. |
| `auth.stored` | Whether lairen recorded a credential copy. The blob itself lives in `credentials.json`. |
| `auth.captured_at` | When the stored copy was last captured. |
| `auth.source_home` | Home the stored copy came from. Provenance only. |
| `holder` | At most one live home, or `null`. |
| `holder.stale` | `null` or `{since, reason}`. Advisory; never blocks link/env. |
| `alias` | Optional stable short handle. |
| `extra` | Provider-specific non-secret identity metadata. |

`alias` is optional and holds the user-chosen short handle. `extra` can contain
an email address, account identifiers, or a device id, so treat the registry as
private even though it holds no secrets.

Writes go through a temporary file, `fsync`, and `os.replace`, so a crash does
not leave a half-written registry.

A holder is a property of the account. lairen 2.x has no separate
`holders.json`.

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

The whole file is written atomically with mode `0600`.

`auth.stored` records intent; `lairen status` and `deploy copy` verify the blob
is actually present.

## Snapshots

Before `deploy copy` overwrites an existing target credential, it copies the
target to:

```text
<state>/snapshots/<provider>-<UTC timestamp>/<credential relpath>
```

For example:

```text
~/.local/share/lairen/state/snapshots/codex-20261112T120000000000Z/auth.json
```

Snapshots are ordinary files with mode `0600`. They are never pruned
automatically; delete old timestamp directories when you no longer need them.
Use `--no-backup` to skip snapshot creation for a deployment.

`deploy link` creates a symlink and does not snapshot.

## Deployment log

`<state>/deployments.jsonl` is an append-only JSON Lines history written by
`deploy copy`, `deploy link`, `deploy unlink`, `account sync`, `account
update`, `account set-home`, `account clear-home`, and `account remove`. No
token material is written.

Deployment entries (`action` is `deploy` or `link`) carry a `mode`:

```json
{
  "ts": "2026-11-12T04:20:00+00:00",
  "action": "deploy",
  "mode": "copy",
  "provider": "codex",
  "ref": "codex/alice@example.com",
  "alias": "aj",
  "project": "/home/alice/code/project-b",
  "home": "/home/alice/code/project-b/.codex",
  "source_home": "/home/alice/codex-holders/codex-aj"
}
```

Link entries use `"action": "link"` and `"mode": "link"`; `home` is the project
symlink path and `source_home` is the holder home.

`status` uses `deploy` and `link` entries for other-project reporting. `sync`
entries do not create a project lease.

## Migration details

`lairen migrate` from v1/v2:

1. Backs up the registry, deployment log, and schema marker.
2. Converts accounts to the `auth` + `holder` shape.
3. Keeps old `source_home` as `auth.source_home`.
4. Moves legacy `last_deployed_at` / `last_deployed_home` values into the
   deployment log when no deployment entry exists.
5. Adds `mode: "copy"` to existing deployment entries.
6. Writes the v3 marker.

It does not adopt `source_home` as a holder. It prints candidate homes:

```text
holder unset   : 1
  codex/alice@example.com  --home /home/alice/codex-holders/codex-aj
  fix: lairen account set-home REF --home PATH
```

Attach holders explicitly after migration.
