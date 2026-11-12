# Changelog

All notable changes to lairen are documented here.

## 2.0.0 - 2026-11-12

This is a breaking redesign. The account is now the aggregate root, and the
holder home is part of the account record instead of a separate registry.

### Added

- Accounts now carry `auth` metadata (`stored`, `captured_at`, `source_home`)
  and at most one `holder` (`home`, `recorded_at`, `verified_at`, `stale`).
- `lairen account` group: `add`, `list`, `show`, `update`, `sync`, `set-home`,
  `clear-home`, `alias`, `usage` (`stats`), `scan`, and `remove`.
- `lairen deploy link` symlinks a project home to the account holder.
- `lairen deploy env` prints shell exports for POSIX, fish, csh, PowerShell,
  and nushell.
- `lairen deploy unlink` safely removes a project symlink.
- `deploy copy` marks an account holder `possibly-stale` when the copy target
  is not the holder. The mark never blocks `link` or `env`.
- `status --strict` fails on stale, missing, or logged-out holders and prints
  the reason plus the repair command.
- `status` reports `source` (`copy`/`link`), holder state, links, and shell
  bindings through the provider environment variable.
- JSON payloads for accounts, deployments, and status now expose the nested
  auth/holder/deployment model.

### Changed

- State schema is v3. Commands require migration from v1/v2.
- `lairen migrate` converts account records to the `auth`/`holder` shape,
  moves `last_deployed_*` bookkeeping into the deployment log, and adds
  `mode=copy` to existing deployment entries.
- Migration does not adopt the old `source_home` as a holder. It reports the
  candidate homes and requires `lairen account set-home REF --home PATH`.
- Deployment log entries now record a `mode` (`copy` or `link`), and link
  entries participate in account/project deployment listings.
- `deploy copy --sync` replaces `deploy --refresh`.
- `account list --available` replaces the old `available` command.
- `deploy list` replaces the old `associations` command.

### Removed

The old top-level commands are removed with no aliases:

| Removed | Replacement |
|---|---|
| `lairen register` | `lairen account add` |
| `lairen update` | `lairen account update` |
| `lairen sync` | `lairen account sync` |
| `lairen list` | `lairen account list` |
| `lairen show` | `lairen account show` |
| `lairen alias` | `lairen account alias` |
| `lairen remove` | `lairen account remove` |
| `lairen usage` / `stats` | `lairen account usage` / `account stats` |
| `lairen scan` | `lairen account scan` |
| `lairen deploy REF` | `lairen deploy copy REF` |
| `lairen associations` | `lairen deploy list` |
| `lairen available` | `lairen account list --available` |

## 1.5.0 - 2026-11-09

### Added

- `lairen associations [--group-by account|project] [--account REF]...
  [--project DIR]... [--provider P]... [--active-only] [--json]` derives the
  account/project graph from the deployment ledger. The newest deploy for each
  `(provider, home)` pair is active; older entries are overwritten. An
  `update` that changes an account's identity also invalidates earlier
  deployments of that account. Several providers and several homes per project
  are supported, including custom home directory names.
- `lairen available [--provider P]... [--json]` lists registered accounts with
  no active deployment. Overwritten assignments do not count as assigned.
- `lairen deploy --project PATH` attributes a deployment to a project and
  resolves a relative `--home` under it.
- `lairen deploy` no longer requires `--home`. Omitting it uses
  `<project>/<provider native name>` (`.kimi-code`, `.codex`, `.claude`,
  `.commandcode`, `.opencode`). Cursor keeps requiring an explicit `--home`.
- Deploy records now store the resolved `project` explicitly, so custom home
  directory names keep their project association.
- `lairen migrate [--dry-run] [--project HOME=PROJECT]... [--no-backup]`
  explicitly migrates old lairen state to the current schema. It backfills
  project attribution, materializes legacy `last_deployed_home` pointers as
  deploy entries, and refuses versions below the supported minimum. Re-running
  with `--project` on a current state applies late mappings to unattributed
  entries.
- `data/schema.json` now records the on-disk state version. Fresh state gets
  the current version; existing state without a marker is legacy and must be
  migrated.

### Changed

- Commands no longer read legacy deployment-log or `last_deployed_home`
  fallbacks at runtime. Unmigrated state fails with a `lairen migrate` hint,
  and `lairen doctor` reports the schema status.

## 1.4.0 - 2026-10-28

### Added

- `lairen deploy` now refuses to overwrite a target whose live credential is
  newer than the stored copy for that account. The refusal names the account,
  explains that overwriting would discard a newer token, and prints the
  `lairen sync` command that captures it first.
- `lairen deploy --force` overrides the refusal. The normal pre-deploy snapshot
  still preserves the overwritten file. A target holding an unregistered
  credential produces a warning rather than a refusal.

## 1.3.0 - 2026-10-27

Adds a sync path that pulls refreshed credentials back into the store.

### Added

- `lairen sync [REF ...] [--home PATH ...] [--dry-run] [--strict]` reads known
  deployed homes and the source home, keeps the freshest same-identity
  credential, and writes it back to the store. It never writes a provider home.
  Identity changes are reported and require `lairen update`.
- `lairen deploy --refresh` syncs known homes and the existing target before
  writing, so a target that already refreshed its tokens is captured instead
  of overwritten.
- `sync` appends `sync` entries to `state/deployments.jsonl`; `status` continues
  to use `deploy` entries for lease reporting.

### Changed

- Deployment-log writing is shared through `record_event()`.
- The agent-oriented manual and docs now recommend `lairen sync` before
  redeploying an account that another home has used.

## 1.2.0 - 2026-10-26

Adds a project-aware status view and an append-only deployment ledger.

### Added

- `lairen status [DIRECTORY]` reports which accounts a project's `.codex` and
  `.kimi-code` homes are using, including aliases, expiry, unregistered or
  invalid credentials, drift from the registry, and other projects holding the
  same account.
- Append-only `state/deployments.jsonl` records deploy, update, and remove
  events. `status` uses it for lease reporting; older deployments fall back to
  `last_deployed_home`.
- `status --json` and `status --strict` for scripts and CI.

## 1.1.0 - 2026-10-26

Adds one-line credential updates for retired or refreshed logins.

### Added

- `lairen update REF --home PATH` replaces a stored credential from a new
  provider home in one command. It preserves the alias and custom label,
  follows a changed account identity, removes the old credential blob, and
  refuses to merge with another existing account.

## 1.0.0 - 2026-10-26

First stable release. lairen's CLI surface and registry format are now covered
by a stability commitment: registry changes remain backward compatible and
existing refs continue to resolve.

### Added

- First-class account aliases, managed with `lairen alias [REF] [NAME]`,
  `lairen alias REF --clear`, and `lairen alias --json`.
- `lairen register --alias NAME` sets an alias while saving a login.
- Aliases resolve before bare ids and labels; `provider/id` remains exact.
- Alias validation rejects duplicates and conflicts with account ids or
  labels, and enforces the short-handle character and length rules.
- Re-registration through `lairen register` or `lairen scan --register`
  preserves an existing alias.
- `lairen list` gained an `ALIAS` column, and `list`, `usage`, and `show` JSON
  records include an `alias` field.
- Documentation and the agent-oriented `lairen manual` cover alias creation,
  resolution, validation, and JSON output.

### Changed

- Registry records gained an optional `alias` field. Existing `registry.json`
  files load without migration.
- The text output of `lairen list` gained a column. Scripts that parse the
  table should use `lairen list --json`.
- Version 1.0.0 marks the first stable release. No upgrade steps are required.

[1.5.0]: https://github.com/igamenovoer/lairen/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/igamenovoer/lairen/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/igamenovoer/lairen/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/igamenovoer/lairen/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/igamenovoer/lairen/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/igamenovoer/lairen/compare/v0.2.0...v1.0.0
