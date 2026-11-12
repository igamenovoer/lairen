# Quick start

This walkthrough records a Codex login, inspects it, deploys it three ways,
pulls refreshed auth back into lairen, and checks a project. The Kimi path
works the same way with a Kimi home.

lairen never prints access tokens or refresh tokens. Commands print account
references, labels, paths, holder state, and expiry metadata only.

## 1. Find an existing login

Point `account scan` at a directory that contains provider homes. Depth `1`
inspects the directory itself plus its immediate children.

```bash
lairen account scan ~/code --depth 2
```

```text
PROVIDER  REF                      HOME                              DEPTH
codex     codex/alice@example.com  /home/alice/code/project-a/.codex  2
kimi      kimi/u_123--d_456       /home/alice/kimi-homes/kimi-1      1
```

See [Scan for accounts](../guides/scanning.md) for pattern details and
`--add`.

## 2. Add the account

```bash
lairen account add --provider codex \
  --home ~/codex-holders/codex-aj --alias aj
```

```text
account codex/alice@example.com  alias=aj  auth=stored  holder=/home/alice/codex-holders/codex-aj  state=ok
```

`account add` reads the live credential, derives the identity, stores auth, and
records the home as the account holder. The holder home is left untouched.

Useful variants:

```bash
# Record a holder without copying the credential into lairen.
lairen account add --provider codex --home ~/codex-holders/codex-temp --holder-only

# Store auth without recording a holder.
lairen account add --provider codex --home ~/tmp/codex-once --no-holder

# Add every discovered account, newest copy per identity.
lairen account scan ~/codex-holders --depth 1 --add
```

## 3. Inspect the account

```bash
lairen account list
```

```text
REF                       ALIAS  LABEL              AUTH    HOLDER                            HOLDER STATE     DEPLOYED
codex/alice@example.com   aj     alice@example.com  stored  /home/alice/codex-holders/codex-aj  ok              -
```

`account show` adds auth metadata, live holder identity, usage, and
deployments:

```bash
lairen account show aj
lairen account show aj --json
```

`account usage` prints expiry for every account:

```bash
lairen account usage
lairen account usage --json
```

`stats` is an alias for `account usage`.

## 4. Deploy by copying

```bash
cd ~/code/project-b
lairen deploy copy aj                     # ./.codex
lairen deploy copy aj --home .codex-2     # custom target name
lairen deploy copy aj --project ~/code/project-b
```

```text
target: /home/alice/code/project-b/.codex
deployed codex/alice@example.com -> /home/alice/code/project-b/.codex/auth.json
snapshot: /home/alice/.local/share/lairen/state/snapshots/codex-20261112T120000000000Z/auth.json
note: holder /home/alice/codex-holders/codex-aj is now possibly stale; ...
```

Copying to a home other than the holder marks the holder possibly stale. The
copy still succeeds. If the target already existed, lairen saved a snapshot
before replacing it. Pass `--no-backup` to skip it.

`--sync` pulls fresher auth from the holder or known deployments before
writing:

```bash
lairen deploy copy aj --project ~/code/project-b --sync
```

## 5. Deploy by linking

```bash
lairen deploy link aj --project ~/code/project-a
```

```text
linked codex/alice@example.com -> /home/alice/code/project-a/.codex  home=/home/alice/codex-holders/codex-aj
```

The project gets a symlink, not a copy. Sessions, caches, and refreshed tokens
stay in the holder home. `deploy link` refuses to replace a real directory; it
replaces another symlink only with `--force`.

Remove a project link with:

```bash
lairen deploy unlink aj --project ~/code/project-a --yes
```

## 6. Deploy into the current shell

```bash
eval "$(lairen deploy env aj)"
```

For Bash/Zsh this prints:

```text
export CODEX_HOME='/home/alice/codex-holders/codex-aj'
```

`--shell fish`, `csh`, `tcsh`, `powershell`, `pwsh`, `nu`, and `nushell` are
supported. `auto` detects from `$SHELL` and defaults to POSIX `sh`.

`env` prints the command to stdout and warnings to stderr, so `eval` is safe.

## 7. Pull refreshed auth back

The holder or a deployed home may refresh its tokens. Capture the freshest
same-identity credential into lairen's store:

```bash
lairen account sync aj
lairen account sync aj --home ~/codex-holders/codex-aj
lairen account sync aj --holder-only
lairen account sync aj --dry-run
```

`sync` never changes the holder. Use `account set-home` for that.

## 8. Check a project

```bash
cd ~/code/project-b
lairen status
lairen status --json
lairen status --strict
```

`status` reads the project's live homes and reports the account, source
(`copy`/`link`), auth state, holder state, expiry, and other projects. It also
reports a shell binding when `CODEX_HOME`/`KIMI_CODE_HOME` points at a holder.

`--strict` exits 1 for unregistered, invalid, drifted (copy source),
missing-auth (copy source), stale holder, missing holder, and logged-out
holder states. The error names the
reason and the repair command.

## 9. Replace the holder

```bash
lairen account set-home aj --home ~/codex-holders/codex-aj-v2
lairen account set-home aj --home ~/codex-holders/codex-aj-v2 --sync
```

The new home must hold the same identity. If the identity changed, use
`account update`:

```bash
lairen account update aj --home ~/kimi-homes/kimi-2064-2
```

`update` refreshes auth, sets the new holder, and keeps the alias. The ref may
change when the identity changes.

## 10. Remove an account

```bash
lairen account remove aj --yes
```

This deletes the account record and stored auth. Holder homes and project
symlinks remain on disk. The command warns about active links.

## Migrating from lairen 1.x

Schema v3 is required. Commands refuse old state until you migrate:

```bash
lairen migrate --dry-run
lairen migrate
```

Migration converts `source_home` to `auth.source_home` but does **not** adopt
it as a holder. It reports candidate homes:

```text
holder unset   : 1
  codex/alice@example.com  --home /home/alice/codex-holders/codex-aj
  fix: lairen account set-home REF --home PATH
```

Attach holders explicitly:

```bash
lairen account set-home codex/alice@example.com \
  --home /home/alice/codex-holders/codex-aj
```

## Working as an agent

```bash
lairen manual all
lairen manual all --json
```

Individual topics are available through `lairen manual <topic>`; see the
[CLI reference](../reference/cli.md#manual).

## Next steps

- [Identities and refs](../concepts/identities.md): why Kimi refs include a device id.
- [Deploy an account](../guides/deploying.md): copy, link, env, and staleness.
- [Storage and paths](../concepts/storage.md): the v3 account record.
