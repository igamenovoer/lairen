# Scan for accounts

`lairen scan` walks a directory tree looking for Codex and Kimi credential
homes. It validates each candidate by parsing the credential JSON, so a file
named `auth.json` that does not contain a Codex login is ignored.

```bash
lairen scan DIRECTORY [--depth N] [--provider codex|kimi] [--register] [--json]
```

Scanning only supports `codex` and `kimi`. The other adapters are registerable
by path but are not auto-discovered.

## Depth semantics

`--depth` counts directory levels **below** the scan root. The default is `1`.

| `--depth` | Directories inspected |
|---:|---|
| `0` | The root directory only |
| `1` | The root and its immediate children |
| `2` | The root, its children, and their children |
| `N` | Every directory up to `N` levels below the root |

The root itself is always inspected. This matters because a scan root can be a
provider home:

```bash
# ~/code/project/.codex is two levels below ~/code
lairen scan ~/code --depth 2

# ~/kimi-homes/kimi-1 is one level below ~/kimi-homes
lairen scan ~/kimi-homes --depth 1
```

Symlinked directories are not followed. Unreadable directories and files are
skipped without aborting the scan.

## Candidate patterns

For every inspected directory `<dir>`, lairen checks:

| Provider | Candidate credential files |
|---|---|
| `codex` | `<dir>/auth.json`, `<dir>/.codex/auth.json` |
| `kimi` | `<dir>/credentials/*.json`, `<dir>/.kimi-code/credentials/*.json`, `<dir>/.kimi/credentials/*.json` |

The Kimi glob covers the standard `kimi-code.json` file and environment-scoped
names such as `kimi-code-env-*.json`.

## Validation

A candidate is reported only when its JSON shape matches the provider:

- **Codex**: an object with a `tokens` object, or an `OPENAI_API_KEY` field, or
  an `auth_mode` field.
- **Kimi**: an object with `access_token` or `refresh_token`, plus at least one
  of `scope`, `expires_at`, or `token_type`.

If identity extraction fails, the candidate is skipped. See
[Identities and refs](../concepts/identities.md) for the fields lairen reads.

## Ignored directories

The scanner does not descend into common noise directories:

```text
.cache  .git  .hg  .mypy_cache  .pixi  .pytest_cache  .ruff_cache
.svn  .tox  .venv  __pycache__  build  dist  node_modules
site-packages  target  venv
```

The root itself is always inspected, even when its name appears in this list.

## Report mode

Without `--register`, `scan` prints a table:

```text
PROVIDER  REF                          HOME                                  DEPTH
codex     codex/alice@example.com      /home/alice/code/project-a/.codex     2
codex     codex/alice@example.com      /home/alice/code/project-b/.codex     2
kimi      kimi/u_123--d_456            /home/alice/kimi-homes/kimi-1         1
```

Duplicate copies of one account are listed separately in report mode, including
backup files. Use the table to decide which home is authoritative.

When nothing matches:

```text
no accounts found under /home/alice/code (depth=2)
```

The command exits successfully.

### JSON output

`--json` emits the same findings as a JSON list:

```json
[
  {
    "provider": "codex",
    "ref": "codex/alice@example.com",
    "label": "alice@example.com",
    "home": "/home/alice/code/project-a/.codex",
    "credential": "/home/alice/code/project-a/.codex/auth.json",
    "depth": 2
  }
]
```

## Register discovered accounts

`--register` saves one account per `provider + id`. When the same account
appears in several homes, lairen keeps the copy with the newest file
modification time:

```bash
lairen scan ~/code --depth 2 --register
```

```text
registered codex/alice@example.com  source=/home/alice/code/project-b/.codex
registered kimi/u_123--d_456  source=/home/alice/kimi-homes/kimi-1
```

Notes:

- `--register` prints registration lines instead of the discovery table.
- `--json` is ignored when `--register` is present; registration has already
  happened by the time output would be emitted.
- Re-registering an existing `provider/id` updates its metadata and credential
  blob. It does not create a duplicate, and an existing alias is preserved.
- Backup copies are valid candidates. Because the newest copy wins, scan a tree
  that contains the copy you actually want to keep, or register the intended
  home explicitly with `lairen register`.

## Limit providers

`--provider` is repeatable and restricts the scan:

```bash
lairen scan ~/kimi-homes --provider kimi
lairen scan ~/code --provider codex --provider kimi
```

Omitting it scans both providers.

## Related commands

- `lairen register <provider> --home PATH`: register one specific home.
- `lairen list`: list saved accounts.
- `lairen deploy <ref> --home PATH`: materialize a saved account.
