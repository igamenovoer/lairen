# CLI reference

```text
lairen [--version] [-h | --help] COMMAND [ARGS]...
```

Global options:

| Option | Meaning |
|---|---|
| `--version` | Print `lairen, version <version>` and exit. |
| `-h`, `--help` | Show help for the group or a command. |

Top-level commands:

| Command | Purpose |
|---|---|
| [`account`](#account) | Account identity, stored auth, holder home, aliases, usage |
| [`deploy`](#deploy) | Copy, link, env, list, and unlink deployments |
| [`status`](#status) | Inspect the project directory in front of you |
| [`providers`](#providers) | Provider defaults and adapter status |
| [`doctor`](#doctor) | Paths, counts, schema, and holder health |
| [`migrate`](#migrate) | Migrate state to schema v3 |
| [`manual`](#manual) | Agent-oriented usage manual |

Refs are `provider/id`, a unique alias, a unique bare id, or a unique label.
See [Identities and refs](../concepts/identities.md).

## account

```text
lairen account [COMMAND]
```

An account is one credential identity accepted by a provider CLI. It has at
most one holder home. It may also keep a credential copy inside lairen.

### account add

```text
lairen account add --provider P --home PATH
                   [--alias NAME] [--label TEXT]
                   [--holder-only | --no-holder] [--json]
```

Reads a live provider home, creates or refreshes the account, and stores auth
by default. The same home becomes the holder unless `--no-holder` is given.

| Option | Meaning |
|---|---|
| `--provider P` | Provider adapter. Required. |
| `--home PATH` | Existing, pre-logged-in provider home. Required. |
| `--alias NAME` | Stable short handle. |
| `--label TEXT` | Override the display label. |
| `--holder-only` | Record the holder without copying auth into lairen. |
| `--no-holder` | Store auth without recording a holder. |
| `--json` | Emit the full account payload. |

`--holder-only` and `--no-holder` are mutually exclusive. Re-adding an account
preserves an existing alias and custom label unless overridden.

```bash
lairen account add --provider codex --home ~/codex-holders/codex-aj --alias aj
lairen account add --provider codex --home ~/tmp/codex --holder-only
```

### account list

```text
lairen account list [--provider P ...] [--available]
                    [--with-holder] [--stale-holders] [--json]
```

Prints `REF`, `ALIAS`, `LABEL`, `AUTH`, `HOLDER`, `HOLDER STATE`, and
`DEPLOYED`.

| Option | Meaning |
|---|---|
| `--provider P` | Limit to one provider. Repeatable. |
| `--available` | Only accounts with no active deployment. |
| `--with-holder` | Only accounts with a holder home. |
| `--stale-holders` | Only accounts whose holder is possibly stale. |
| `--json` | Emit full account payloads with deployments. |

`--available` replaces the old top-level `available` command.

### account show

```text
lairen account show REF [--json]
```

Shows identity, alias, label, stored auth metadata, holder state, deployments,
and live holder usage. JSON output includes nested `auth`, `holder`, and
`deployments` objects.

### account update

```text
lairen account update REF --home PATH [--label TEXT] [--keep-home] [--json]
```

Reads a new credential from `--home`, replaces stored auth, and sets the new
home as the holder. The identity may change; the ref follows it and the alias
survives.

| Option | Meaning |
|---|---|
| `--home PATH` | Provider home with the new credential. Required. |
| `--label TEXT` | Override the display label. |
| `--keep-home` | Keep the existing holder. Rejected when the identity changes. |
| `--json` | Emit the updated account payload. |

### account sync

```text
lairen account sync [REF ...] [--home PATH ...] [--holder-only]
                    [--dry-run] [--strict] [--json]
```

Pulls the freshest same-identity credential from the holder and known deployed
homes into the store. `sync` never changes the holder.

| Option | Meaning |
|---|---|
| `--home PATH` | Use only these homes. Requires exactly one REF. Repeatable. |
| `--holder-only` | Read only the account holder. Cannot combine with `--home`. |
| `--dry-run` | Report what would change without writing. |
| `--strict` | Exit 1 when drift remains or a source cannot be used. |
| `--json` | Emit sync results. |

When the holder is read and its credential is current, `sync` clears a
`possibly-stale` mark.

### account set-home

```text
lairen account set-home REF --home PATH [--sync] [--json]
```

Attaches or replaces the holder. The home must hold the same identity; a
different identity is rejected with a pointer to `account update`.

`--sync` also captures auth from the new home. `set-home` clears a stale mark.

### account clear-home

```text
lairen account clear-home REF [--json]
```

Forgets the holder pointer. Stored auth and the home itself are untouched.

### account alias

```text
lairen account alias [REF] [NAME] [--clear] [--json]
```

Sets, clears, or lists aliases. With no arguments, lists non-empty aliases.
`REF NAME` sets an alias; `REF --clear` removes it; `REF` prints the current
alias.

### account usage

```text
lairen account usage [REF ...] [--json]
```

Shows access expiry, remaining time, and holder state from stored auth.
`account stats` is an alias.

### account scan

```text
lairen account scan DIRECTORY [--depth N] [--provider P]
                    [--add] [--holder-only] [--json]
```

Discovers Codex and Kimi homes. Depth `0` checks only the root; depth `1`
(the default) also checks immediate children.

| Option | Meaning |
|---|---|
| `--depth N` | Directory levels below the root. |
| `--provider P` | Limit discovery to `codex` or `kimi`. Repeatable. |
| `--add` | Create accounts for discovered homes. |
| `--holder-only` | With `--add`, record holders without storing auth. |
| `--json` | Emit scan hits. |

With `--add`, duplicate copies of one identity keep the newest credential.

### account remove

```text
lairen account remove REF --yes [--json]
```

Deletes the account record and stored auth. Holder homes, project symlinks,
and snapshots remain on disk. Active links are reported as warnings.

## deploy

```text
lairen deploy [COMMAND]
```

Deployment modes:

| Mode | Meaning |
|---|---|
| `copy` | Write stored auth into a project home. |
| `link` | Symlink a project home to the account holder. |
| `env` | Print an export that points the shell at the holder. |

### deploy copy

```text
lairen deploy copy REF [--project P] [--home PATH]
                   [--sync] [--force] [--no-backup]
```

Requires stored auth. If the target already exists, lairen snapshots it and
refuses to overwrite a newer credential for the same or another account unless
`--force` is given.

- `--sync` first runs `account sync` for the account.
- Omitting `--home` uses `<project>/<provider project home>`.
- A relative `--home` resolves under `--project` or the current directory.
- Cursor has no project home name; pass `--home`.

If the account has a holder and the target is not the holder, the holder is
marked `possibly-stale` after a successful copy. The copy still succeeds. If
the target is the holder itself, the stale mark is cleared.

### deploy link

```text
lairen deploy link REF [--project P] [--home PATH] [--force]
```

Requires a holder home. Creates `<project>/<provider project home>` as a
symlink to the holder.

- A symlink already pointing at the holder is a no-op.
- A symlink to another target is replaced only with `--force`.
- A real directory or file is never replaced. Move it aside first.
- A stale holder produces a warning on stderr but the link is created.

### deploy env

```text
lairen deploy env REF [--shell auto|sh|bash|zsh|fish|csh|tcsh|powershell|pwsh|nu]
```

Prints one export command on stdout. Warnings go to stderr.

```bash
eval "$(lairen deploy env aj)"
```

`auto` detects from `$SHELL` and defaults to POSIX `sh`. Providers without an
environment variable (Cursor) are rejected with a pointer to `deploy link`.

### deploy list

```text
lairen deploy list [--account REF ...] [--project P ...] [--provider P ...]
                   [--mode copy|link ...] [--group-by account|project]
                   [--active-only] [--json]
```

Lists copy and link deployments from the ledger. The newest deployment for a
`(provider, home)` pair is `active`; older entries are `overwritten`.
Identity-changing updates also overwrite earlier deployments.

JSON records include `mode` and `source_home`. `deploy list` replaces the old
top-level `associations` command.

### deploy unlink

```text
lairen deploy unlink REF [--project P] [--home PATH] --yes [--json]
```

Removes a project symlink only when it points at the account's holder. It
refuses real directories and symlinks to other targets.

## status

```text
lairen status [DIRECTORY] [--provider codex|kimi ...] [--json] [--strict]
```

Reads the project's live provider homes and reports:

- account ref, alias, and label
- source: `copy`, `link`, or shell binding
- auth state: `current`, `unregistered`, `invalid`, `drifted`, `missing-auth`
  (`drifted` is informational for a `link` source, where the holder is live)
- holder state: `ok`, `possibly-stale`, `missing`, `no-login`, `none`
- access expiry and other projects from the deployment ledger

`--strict` exits 1 when a problem remains. Problems include auth problems and
holder problems. The error names each account, the reason, and the fix:

```text
strict status failed: 1 problem(s)
  codex/alice@example.com: holder /home/me/codex-holders/codex-aj is possibly stale
    (since 2026-11-12T04:20:00+00:00: deploy copy -> /home/me/code/project-b/.codex)
    fix: lairen account sync codex/alice@example.com --home /home/me/codex-holders/codex-aj
```

A shell binding is reported when the current environment's provider home
variable points at a registered holder:

```text
shell: CODEX_HOME=/home/me/codex-holders/codex-aj  account=codex/alice@example.com  holder_state=ok
```

## providers

```text
lairen providers
```

Prints provider name, tested status, environment variable, default home,
project home name, credential relative path, and notes.

## doctor

```text
lairen doctor
```

Prints resolved config/data/state paths, schema status, account count, stored
auth count, holder count, stale holder count, and the login status of each
provider's default home. `doctor` works without migrating old state so it can
diagnose it.

## migrate

```text
lairen migrate [--dry-run] [--project HOME=PROJECT ...] [--no-backup]
```

Migrates state to schema v3. Commands refuse v1/v2 state until this completes.

The migration:

- converts each account to `auth` + `holder: null`
- keeps the old `source_home` as `auth.source_home`
- moves legacy `last_deployed_*` bookkeeping into the deployment log
- adds `mode=copy` to existing deployment entries
- writes the v3 marker
- reports accounts whose old `source_home` is available

It never adopts a holder automatically. Attach one explicitly:

```bash
lairen account set-home REF --home PATH
```

`--project HOME=PROJECT` maps a custom home to a project. Re-running with
`--project` on v3 applies late mappings to unattributed deployment entries.

## manual

```text
lairen manual [TOPIC] [--json]
```

Topics: `overview`, `commands`, `workflows`, `providers`, `storage`, `json`,
`safety`, and `all`.

```bash
lairen manual all
lairen manual all --json
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | A lairen domain error, failed strict check, or refused operation. |
| `2` | Click usage error. |

## JSON output

Commands with JSON output:

```text
lairen account list --json
lairen account show REF --json
lairen account sync --json
lairen account scan DIR --json
lairen deploy list --json
lairen deploy unlink REF --json
lairen status DIR --json
lairen manual all --json
```

See `lairen manual json` for the current shapes.
