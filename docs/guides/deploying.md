# Deploy credentials

`deploy` writes a saved credential into a target provider home. The target is
always an explicit `--home` argument, and any existing credential is
snapshotted before it is replaced.

```bash
lairen deploy REF --home PATH [--no-backup]
```

## Target home resolution

`--home` names the provider home directory, not the credential file:

| Provider | Pass | lairen writes |
|---|---|---|
| `codex` | `--home ./project/.codex` | `./project/.codex/auth.json` |
| `kimi` | `--home ./project/.kimi-code` | `./project/.kimi-code/credentials/<name>.json` |
| `claude` | `--home ./project/.claude` | `.credentials.json`, plus `oauthAccount` in `.claude.json` |
| `commandcode` | `--home ./project/.commandcode` | `auth.json` |
| `cursor` | `--home ~/.config/Cursor/User/globalStorage` | `state.vscdb` |
| `opencode` | `--home ./project/opencode` | `auth.json` |

Tilde expansion and relative paths are supported. Missing parent directories
are created during the write. For `cursor`, the target `state.vscdb` must
already exist; lairen does not create a Cursor database from scratch.

For Kimi, lairen always writes `credentials/kimi-code.json` in the target home,
regardless of the source file's name. `scan` can discover environment-scoped
files such as `kimi-code-env-*.json`; deploying one normalizes it to the
standard name.

## Resolution of REF

`REF` follows the rules in [Identities and refs](../concepts/identities.md):

```bash
lairen deploy codex/alice@example.com --home ./project/.codex
lairen deploy 'alice@example.com' --home ./project/.codex
```

The full `provider/id` form is the only unambiguous choice when ids or labels
collide.

## What deploy does

1. Resolves the account in the registry.
2. Loads the credential blob from the store.
3. Reads any existing target credential.
4. Copies the existing target into a snapshot directory unless `--no-backup`
   is set.
5. Composes the new file contents. Most providers replace the file; a few merge
   into an existing structure (see below).
6. Writes atomically with mode `0600`.
7. Records `last_deployed_at` and `last_deployed_home` in the registry.

Output:

```text
deployed codex/alice@example.com -> /home/alice/project/.codex/auth.json
snapshot: /home/alice/.local/share/lairen/state/snapshots/codex-20261026T120000000000Z/auth.json
```

The snapshot line appears only when a target file existed and backups were
enabled.

## Replace versus merge

| Provider | Behavior |
|---|---|
| `codex` | Replaces `auth.json` with the saved blob. |
| `kimi` | Replaces the credential file with the saved blob. |
| `claude` | Replaces `.credentials.json`, then merges `oauthAccount` fields into `.claude.json`. |
| `commandcode` | Writes `{"apiKey": "<key>"}` to `auth.json`. |
| `cursor` | Updates Cursor's `ItemTable` keys in place; other rows are preserved. |
| `opencode` | Preserves other `auth.json` slots and replaces only `opencode-go`. |

Merging providers still create a snapshot of the file they modify.

## Snapshots and rollback

Snapshots live under the state directory:

```text
<state>/snapshots/<provider>-<UTC timestamp>/<credential relpath>
```

To roll back a Codex deployment:

```bash
cp ~/.local/share/lairen/state/snapshots/codex-20261026T120000000000Z/auth.json \
  ~/project/.codex/auth.json
chmod 600 ~/project/.codex/auth.json
```

Snapshots are never pruned automatically. Delete old timestamp directories when
they are no longer useful.

Use `--no-backup` when the target is disposable or when a script already
manages backups:

```bash
lairen deploy codex/alice@example.com --home /tmp/worktree/.codex --no-backup
```

## Swapping identities between projects

Given two project-local Codex homes:

```bash
# Capture the login each project currently holds
lairen register codex --home ~/code/project-a/.codex
lairen register codex --home ~/code/project-b/.codex

# Inspect the ids
lairen list

# Put A's account into B and B's account into A
lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
lairen deploy codex/bob@example.com   --home ~/code/project-a/.codex
```

Each deployment snapshots the file it replaces, so both previous project
credentials remain recoverable. Both accounts remain in the registry.

If one project has no login yet, register only the source, then deploy into the
empty target. lairen creates the target home and credential file.

## Verify a deployment

```bash
lairen doctor
lairen show codex/alice@example.com
```

`doctor` reports whether each provider home now contains a login. `show`
reports the account's metadata and the stored blob's expiry, not the contents
of the target file.

## Before you deploy

Stop any running agent that uses the same saved session, and read the
[OAuth rotation rule](../concepts/security.md#oauth-refresh-token-rotation).
Deployment is a copy, not a move; two active homes sharing one refresh token
can invalidate each other.

For Cursor, close the application before deploying so the SQLite database is
not locked.
