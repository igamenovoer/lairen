# Scan for accounts

`lairen account scan` discovers Codex and Kimi credential homes under a
directory tree.

```bash
lairen account scan ~/code --depth 2
lairen account scan ~/codex-holders --provider codex
lairen account scan ~/tmp/workspace --add
lairen account scan ~/code --depth 2 --json
```

## Depth

| Depth | Scope |
|---|---|
| `0` | Only the given directory |
| `1` | The directory plus immediate children (default) |
| `2` | The directory, children, and grandchildren |

The scanner skips symlinked directories and common noise directories:
`.git`, `.hg`, `.svn`, `.pixi`, `.venv`, `venv`, `node_modules`, `build`,
`dist`, caches, and bytecode directories.

## Patterns

Codex:

- `<dir>/auth.json`
- `<dir>/.codex/auth.json`

Kimi:

- `<dir>/credentials/*.json`
- `<dir>/.kimi-code/credentials/*.json`
- `<dir>/.kimi/credentials/*.json`

Candidates are validated by parsing the credential, not by filename alone.

## Report only

Without `--add`, scan is read-only:

```bash
lairen account scan ~/code --depth 2
```

```text
PROVIDER  REF                      HOME                              DEPTH
codex     codex/alice@example.com  /home/me/code/project-a/.codex    2
kimi      kimi/user-1--device-1   /home/me/kimi-homes/kimi-1       1
```

JSON output includes `provider`, `ref`, `label`, `home`, `credential`, and
`depth`.

## Create accounts

```bash
lairen account scan ~/codex-holders --depth 1 --add
```

For each discovered account, `--add`:

- creates or refreshes the account
- stores auth from the newest copy
- records the discovered home as the holder
- preserves an existing alias

`--holder-only` records holders without storing auth:

```bash
lairen account scan ~/codex-holders --add --holder-only
```

Duplicate copies of the same identity are collapsed to the newest credential
file.

## After scanning

```bash
lairen account list
lairen account list --stale-holders
lairen account show REF --json
```

Attach a different holder or capture auth later:

```bash
lairen account set-home REF --home PATH
lairen account sync REF --home PATH
```
