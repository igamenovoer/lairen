# Changelog

All notable changes to lairen are documented here.

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

[1.1.0]: https://github.com/igamenovoer/lairen/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/igamenovoer/lairen/compare/v0.2.0...v1.0.0
