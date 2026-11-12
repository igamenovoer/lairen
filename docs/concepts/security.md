# Security model

lairen handles live credentials. Treat its state directories and every provider
home as private.

## Never printed

lairen never prints access tokens, refresh tokens, or API keys. `account show`,
`account usage`, and every JSON output expose identity metadata, paths,
timestamps, expiry, and holder state only.

## Plaintext at rest

The registry and credential store are plaintext JSON:

- directories are created with mode `0700`
- files are written with mode `0600`
- writes use a temporary file, `fsync`, and `os.replace`
- there is no encryption

Provider homes are also plaintext. Protect them with filesystem permissions.

## Copy versus link

- `deploy copy` duplicates the credential into a project home. The stored copy
  and the target can drift.
- `deploy link` and `deploy env` use the holder home directly. No credential is
  duplicated, but every linked project and shell shares that one live home.

Two agents running against the same holder share the same OAuth session and
token-refresh state. Stop the old agent before starting another when the
provider rotates tokens aggressively.

## Holder staleness

A copy deploy to a home other than the holder can rotate the session and leave
the holder's token file stale. lairen marks the holder `possibly-stale`:

- the mark is advisory
- `link` and `env` still work and warn on stderr
- `deploy copy` still works
- `account sync` from the holder, `account set-home`, and `account update` clear
  the mark
- `status --strict` fails on the mark and prints the reason plus the repair
  command

This is deliberate: lairen records the risk instead of preventing the user from
using the holder.

## Overwrite protection

Before `deploy copy` overwrites a target, it inspects the target credential:

- an unregistered target produces a warning
- a target holding a newer credential for the same account is refused unless
  `--force` is given
- a target holding a newer credential for another account is refused unless
  `--force` is given
- an existing target is snapshotted before replacement unless `--no-backup`

Snapshots are plaintext files with mode `0600`, kept under
`<state>/snapshots/`. They are never pruned automatically.

## Symlink safety

`deploy link`:

- refuses to replace a real directory or file
- replaces an existing symlink only with `--force`
- refuses a target that is already the holder home

`deploy unlink` removes only a symlink that points at the account holder. It
refuses real directories and symlinks to other targets.

## Migration safety

`lairen migrate` backs up the registry, deployment log, and schema marker before
rewriting. Backups live under `<state>/migrations/<UTC timestamp>/`.

Migration never adopts an old `source_home` as a holder. It reports candidate
homes so you can attach them explicitly with `account set-home`.

## Experimental adapters

`claude`, `commandcode`, `cursor`, and `opencode` are implemented against their
upstream storage layouts but have no live-credential tests in this project.
They print a warning on use.

Cursor stores credentials in SQLite. Close Cursor before a copy deploy.

## What not to commit

- `credentials.json`
- `registry.json`
- any provider home
- snapshots or migration backups

The deployment log contains account refs, aliases, project paths, and home
paths. It does not contain token material, but treat it as private too.
