# Security model

lairen manages live credentials for CLI agents. This page states what it
protects, what it does not, and the one operational rule that matters most:
**do not let two active homes refresh the same OAuth session at the same time.**

## Local plaintext storage

The credential store is a plaintext JSON file with mode `0600`, inside
directories created with mode `0700`. This matches how the native clients store
their own credentials. There is no encryption layer and no OS keychain
integration.

Consequences:

- Anyone who can read your user account can read the credentials.
- Backups, snapshots, and disk images contain the credentials.
- The registry is not secret, but it contains emails, source paths, and account
  identifiers.

If your threat model requires encrypted credentials at rest, rely on
full-disk encryption or an external secret manager. lairen does not provide
either.

## Secrets are never printed

`lairen list`, `lairen show`, `lairen usage`, and `lairen scan` print account
metadata, paths, and expiry timestamps. They do not print access tokens,
refresh tokens, or API keys. `lairen providers` and `lairen doctor` print
configuration only.

`lairen show` emits JSON, but that JSON contains the same metadata as
`lairen usage`, not the credential blob.

## Atomic writes and snapshots

Every registry, store, and target-credential write goes through a temporary
file in the destination directory, an `fsync`, and `os.replace`. Readers never
observe a partially written credential.

Before replacing an existing target credential, `deploy` copies it into the
snapshot directory. If a deployment writes the wrong account, you can restore
the previous file by hand:

```bash
cp ~/.local/share/lairen/state/snapshots/codex-20261026T120000000000Z/auth.json \
  ~/code/project-b/.codex/auth.json
chmod 600 ~/code/project-b/.codex/auth.json
```

Snapshot creation is skipped with `--no-backup`. Snapshots are not encrypted
and are not pruned automatically.

## OAuth refresh-token rotation

OAuth providers rotate refresh tokens. When a client refreshes a session, the
provider may invalidate the refresh token that was used and issue a new one.
Two homes holding the same refresh token can therefore invalidate each other:

1. lairen copies a credential blob into project A and project B.
2. Project A starts, refreshes, and writes a new refresh token into its home.
3. Project B starts with the old refresh token, refreshes, and invalidates A's
   new token, or is rejected outright.

lairen cannot prevent this. Copying a credential is not the same as sharing a
session.

### Operational rule

Treat a saved account as a snapshot of one session, and keep one active home
per saved session:

- Stop the agent in the source home before deploying the same account into a
  different home.
- Do not run two agents on the same saved account concurrently.
- If you need concurrent work, register a separate login session for each
  home. For Kimi, each session already has its own `device_id` and ref.
- After a client refreshes a token in the live home, the stored blob is stale.
  Re-run `lairen register` from the live home to capture the refreshed
  credential.

!!! warning "Deployment is a copy"

    `deploy` does not move or delete the source credential. The source home
    keeps working until its token is rotated. The registry copy does not follow
    later refreshes.

## Repository hygiene

Do not commit any of the following:

- `credentials.json` and `registry.json`
- provider homes such as `.codex/` or `.kimi-code/`
- deployment snapshots
- logs that contain token values

The repository `.gitignore` already covers `credentials.json`, `registry.json`,
and common provider-adjacent artifacts, but project-local provider homes must
be ignored by the project that owns them.

## Experimental adapters

`claude`, `commandcode`, `cursor`, and `opencode` are implemented but not
covered by live-credential tests. `register` and `deploy` print a warning to
stderr when one of them is used. Review the [provider reference](../reference/providers.md)
before relying on an experimental adapter with an important account.

## Reporting a vulnerability

Open a private security advisory on the
[GitHub repository](https://github.com/igamenovoer/lairen/security/advisories)
rather than a public issue. Include the affected version, the command, and a
description of the exposure. Never paste live tokens into a report.
