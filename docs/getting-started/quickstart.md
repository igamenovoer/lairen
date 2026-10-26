# Quick start

This walkthrough registers a Codex login, lists it, deploys it into a second
project, and checks its expiry. The Kimi path works the same way with a Kimi
home and a Kimi credential file.

lairen never prints access tokens or refresh tokens. Commands print account
references, labels, paths, and expiry metadata only.

## 1. Find an existing login

Point `scan` at a directory that contains provider homes. Depth `1` inspects the
directory itself plus its immediate children, which covers the common
`<project>/.codex` layout.

```bash
lairen scan ~/code --depth 2
```

```text
PROVIDER  REF                              HOME                              DEPTH
codex     codex/alice@example.com          /home/alice/code/project-a/.codex  2
kimi      kimi/u_123--d_456               /home/alice/kimi-homes/kimi-1      1
```

See [Scan for accounts](../guides/scanning.md) for pattern details and
`--register`.

## 2. Register the login you want to keep

```bash
lairen register codex --home ~/code/project-a/.codex
```

```text
registered codex/alice@example.com  label=alice@example.com  source=/home/alice/code/project-a/.codex
```

lairen reads `auth.json`, derives an account id from the token claims, and
stores the credential blob in its own store. The source home is left untouched.

Use `--label` to override the display label:

```bash
lairen register kimi --home ~/kimi-homes/kimi-1 --label "kimi-lease-1"
```

## 3. Inspect the registry

```bash
lairen list
```

```text
REF                          LABEL              SOURCE                              LAST DEPLOYED
codex/alice@example.com      alice@example.com  /home/alice/code/project-a/.codex   -
kimi/u_123--d_456            kimi-lease-1       /home/alice/kimi-homes/kimi-1       -
```

`lairen show <ref>` prints the full account record plus local usage metadata as
JSON. `lairen usage` prints an expiry table.

## 4. Deploy into a target home

`deploy` always requires an explicit `--home`; lairen never infers a target from
an environment variable.

```bash
lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
```

```text
deployed codex/alice@example.com -> /home/alice/code/project-b/.codex/auth.json
snapshot: /home/alice/.local/share/lairen/state/snapshots/codex-20261026T120000000000Z/auth.json
```

If the target file already existed, lairen saved a copy in its snapshot
directory before replacing it. Pass `--no-backup` to skip the snapshot.

You can also use a bare unique id or label:

```bash
lairen deploy 'alice@example.com' --home ~/code/project-b/.codex
```

See [Deploy credentials](../guides/deploying.md) for resolution rules and
provider-specific merge behavior.

## 5. Check expiry

```bash
lairen usage
```

```text
REF                          ACCESS EXPIRES (UTC)    REMAINING  LAST DEPLOYED
codex/alice@example.com      2026-11-25T12:00:00+00:00  in 30d0h   2026-10-26T12:00:00+00:00
kimi/u_123--d_456            2026-11-01T08:30:00+00:00  in 6d20h   -
```

Machine-readable output:

```bash
lairen usage codex/alice@example.com --json
lairen usage --json
```

`stats` is an alias for `usage`.

## 6. Remove an account

```bash
lairen remove codex/alice@example.com --yes
```

This deletes both the registry record and the stored credential blob. It does
not touch any deployed home or snapshot.

## A complete project swap

To move the active Codex identity from project A to project B while keeping A's
copy recoverable:

```bash
lairen register codex --home ~/code/project-a/.codex
lairen deploy codex/alice@example.com --home ~/code/project-b/.codex
```

Before starting an agent in project B, stop any agent that is still running in
project A. OAuth refresh tokens rotate, and two live homes refreshing the same
token can invalidate each other. The [security model](../concepts/security.md)
explains the mechanics.

## Next steps

- [Identities and refs](../concepts/identities.md): why Kimi refs include a device id.
- [Scan for accounts](../guides/scanning.md): depth semantics and duplicate handling.
- [CLI reference](../reference/cli.md): every option and exit code.
