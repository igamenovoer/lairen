# CLI reference

```text
lairen [--version] [-h | --help] COMMAND [ARGS]...
```

Global options:

| Option | Meaning |
|---|---|
| `--version` | Print `lairen, version <version>` and exit. |
| `-h`, `--help` | Show help for the group or a command. |

Commands:

| Command | Purpose |
|---|---|
| [`register`](#register) | Save the live login from a provider home. |
| [`update`](#update) | Replace a saved credential from a new home. |
| [`list`](#list) | List saved accounts. |
| [`show`](#show) | Show one account and its local usage metadata. |
| [`deploy`](#deploy) | Write a saved credential into a target home. |
| [`sync`](#sync) | Pull refreshed credentials from known homes into the store. |
| [`scan`](#scan) | Discover Codex and Kimi credential homes. |
| [`status`](#status) | Show which accounts a project directory is using. |
| [`usage`](#usage) | Show expiry and usage statistics. |
| [`remove`](#remove) | Remove an account and its stored credential. |
| [`alias`](#alias) | Set, clear, or list stable account aliases. |
| [`providers`](#providers) | Show provider defaults and adapter status. |
| [`doctor`](#doctor) | Show resolved paths, counts, and provider homes. |
| [`manual`](#manual) | Agent-oriented usage manual with examples. |

Refs are `provider/id`, a unique alias, a unique bare id, or a unique label.
See [Identities and refs](../concepts/identities.md).

## register

```text
lairen register [OPTIONS] {claude|codex|commandcode|cursor|kimi|opencode}
```

Reads the live login from a provider home and saves its metadata and credential
blob. The source home is not modified.

| Option | Meaning |
|---|---|
| `--home PATH` | Provider home to read. Falls back to the provider environment variable, then the default home. |
| `--label TEXT` | Override the display label. |
| `--alias TEXT` | Set a stable short handle for the account. |

```bash
lairen register codex --home ~/code/project-a/.codex
lairen register kimi --home ~/kimi-homes/kimi-1 --label "kimi-lease-1" --alias kimi-1
```

Output:

```text
registered <ref>  label=<label>  source=<home>[  alias=<alias>]
```

Registering an existing `provider/id` replaces its metadata and blob but keeps
an existing alias unless `--alias` is given.

For experimental providers, a warning is printed to stderr.

## update

```text
lairen update [OPTIONS] REF
```

Reads a new credential from `--home` and replaces the stored credential for
`REF`. The source home is not modified.

| Option | Meaning |
|---|---|
| `--home PATH` | Provider home to read the new credential from. **Required.** |
| `--label TEXT` | Override the display label. |

```bash
lairen update kimi-2064-1 --home ~/kimi-homes/kimi-2064-1
lairen update codex/alice@example.com --home ~/code/project-a/.codex
```

Output:

```text
updated <ref>  source=<home>[  alias=<alias>]
updated <old-ref> -> <new-ref>  source=<home>[  alias=<alias>]
```

Behavior:

- The account's id and `source_home` follow the new credential.
- The alias is always preserved. A provider-derived label follows a changed
  identity; a custom label is preserved unless `--label` overrides it.
- If the new identity already belongs to another account, lairen refuses to
  merge and names the existing account.
- When the id changes, the old credential blob is removed, the ref changes, and
  the alias continues to resolve to the updated account.
- `created_at` and deployment metadata are preserved. Deploy the account again
  if existing target homes need the new credential.

## list

```text
lairen list [--json]
```

Prints saved accounts, sorted by provider and id:

```text
REF  ALIAS  LABEL  SOURCE  LAST DEPLOYED
```

| Option | Meaning |
|---|---|
| `--json` | Emit the account records as JSON. |

JSON output is a list of account objects with an added `ref` field:

```json
[
  {
    "ref": "codex/alice@example.com",
    "provider": "codex",
    "id": "alice@example.com",
    "label": "alice@example.com",
    "source_home": "/home/alice/code/project-a/.codex",
    "alias": "work",
    "created_at": "2026-10-26T12:00:00+00:00",
    "last_deployed_at": null,
    "last_deployed_home": null,
    "extra": {}
  }
]
```

With no accounts, lairen prints a hint instead of a table:

```text
no accounts; run `lairen register <provider> --home <path>`
```

## show

```text
lairen show REF
```

Prints one JSON object with two keys: `account` (the registry record) and
`usage` (local token metadata). See
[Track usage and expiry](../guides/usage.md#show-one-account).

Exits with an error when the ref is unknown, ambiguous, or has no stored blob.

## deploy

```text
lairen deploy [OPTIONS] REF
```

Writes a saved credential into a target provider home.

| Option | Meaning |
|---|---|
| `--home PATH` | Target provider home. **Required.** |
| `--no-backup` | Skip the pre-deploy snapshot. |
| `--refresh` | Sync refreshed tokens from known homes and the target before writing. |
| `--force` | Overwrite even when the target holds a newer credential. |

```bash
lairen deploy codex/alice@example.com --home ./project/.codex
lairen deploy work --home ./project-c/.codex --refresh
```

Output:

```text
deployed <ref> -> <written credential path>
snapshot: <snapshot path>        # only when a target existed and backups are on
```

Updates `last_deployed_at` and `last_deployed_home` in the registry. See
[Deploy credentials](../guides/deploying.md) for target rules and merge
behavior.

`deploy` copies the stored blob. If another home has used the account and
refreshed its tokens, run `lairen sync REF` first or pass `--refresh`; otherwise
the stale stored copy is what gets written.

Before writing, `deploy` inspects the existing target. If the target holds a
credential for an account in the registry that is newer than the stored copy,
deploy refuses and prints the account, the reason, and the sync command that
would capture it. `--force` overrides the refusal; the pre-deploy snapshot still
protects the old file. A target holding an unregistered credential only prints
a warning.

## sync

```text
lairen sync [REF ...] [--home PATH ...] [--dry-run] [--strict]
```

Reads live credentials from homes that are known to hold the account and copies
the freshest same-identity blob back into the store. It never writes a provider
home.

Candidate homes come from the deployment log and the account's `source_home`.
With `--home`, only the given homes are read and exactly one `REF` is required.

| Option | Meaning |
|---|---|
| `--home PATH` | Provider home to read. Repeatable; restricts the sync to these homes. |
| `--dry-run` | Report what would change without writing. |
| `--strict` | Exit `1` when a drift remains or a source cannot be used. |

```bash
lairen sync
lairen sync kimi-6240-1 --dry-run
lairen sync kimi-6240-1 --home ~/code/project-a/.kimi-code
```

Freshness is compared by refresh-token expiry, then access-token expiry, then
file mtime. A candidate is only written when it is strictly fresher; the alias,
label, and `source_home` are preserved. A home whose credential now belongs to
a different identity is reported and must be rebound explicitly with
[`update`](#update). Each applied sync appends a `sync` entry to the deployment
log.

## scan

```text
lairen scan [OPTIONS] DIRECTORY
```

Walks `DIRECTORY` and reports Codex and Kimi credential homes.

| Option | Meaning |
|---|---|
| `--depth INTEGER` | Directory levels below the root to inspect. Default `1`; must be `>= 0`. |
| `--provider [codex\|kimi]` | Restrict to one provider. Repeatable. |
| `--register` | Save discovered accounts, one per account id, keeping the newest copy. |
| `--json` | Emit findings as JSON. Ignored with `--register`. |

```bash
lairen scan ~/code --depth 2
lairen scan ~/kimi-homes --provider kimi
lairen scan ~/code --depth 2 --register
```

Table columns are `PROVIDER`, `REF`, `HOME`, and `DEPTH`. JSON fields are
`provider`, `ref`, `label`, `home`, `credential`, and `depth`. See
[Scan for accounts](../guides/scanning.md) for patterns and duplicate handling.

## status

```text
lairen status [DIRECTORY] [--provider codex|kimi] [--json] [--strict]
```

Shows which accounts a project directory is using. `DIRECTORY` defaults to the
current directory. lairen reads the project's live credentials rather than the
registry, so manually copied credentials appear too.

Project homes:

| Provider | Home | Credential |
|---|---|---|
| `codex` | `<project>/.codex` | `auth.json` |
| `kimi` | `<project>/.kimi-code` | `credentials/*.json` |

Passing a provider home itself, such as `~/.kimi-code`, inspects that home.

| Option | Meaning |
|---|---|
| `--provider [codex\|kimi]` | Limit the report to one provider. Repeatable. |
| `--json` | Emit the report as JSON. |
| `--strict` | Exit `1` when a credential is unregistered, invalid, drifted, or has no stored blob. |

```bash
lairen status
lairen status ~/code/project-a
lairen status ~/code/project-a --json
lairen status ~/code/project-a --strict
```

States:

| State | Meaning |
|---|---|
| `current` | Registered and the project credential matches the stored blob. |
| `drifted` | Registered identity, but the project blob differs from the store. |
| `unregistered` | Valid credential with no registry record. |
| `invalid` | Unreadable or unparseable credential. |
| `missing-store-blob` | Registry record exists, but its stored blob is missing. |
| `no-login` | The project home exists but contains no credential. |

The `OTHER PROJECTS` column comes from the append-only deployment log and
excludes the inspected home. Each target is checked against its current
credential, so a target that now holds a different account is marked
`(overwritten)`. Accounts recorded before the log existed fall back to the
single `last_deployed_home` value, marked `(last deploy)`. The JSON `leases`
entries carry `live: true|false|null`; `null` means no check was possible.

JSON shape:

```json
{
  "project": "/home/me/code/project-a",
  "ok": true,
  "accounts": [
    {
      "provider": "codex",
      "ref": "codex/alice@example.com",
      "alias": "work",
      "label": "alice@example.com",
      "home": "/home/me/code/project-a/.codex",
      "credential": "/home/me/code/project-a/.codex/auth.json",
      "state": "current",
      "expires_at": "2026-11-25T12:00:00+00:00",
      "expires_in_seconds": 2592000,
      "registry_expires_at": "2026-11-25T12:00:00+00:00",
      "registry_expires_in_seconds": 2592000,
      "leases": [],
      "error": null
    }
  ],
  "warnings": []
}
```

## usage

```text
lairen usage [OPTIONS] [REFS]...
lairen stats [OPTIONS] [REFS]...
```

Prints one row per account with `REF`, `ACCESS EXPIRES (UTC)`, `REMAINING`, and
`LAST DEPLOYED`.

| Option | Meaning |
|---|---|
| `--json` | Emit usage records as JSON. |

With no refs, all accounts are included. `stats` is an alias registered for the
same command.

## remove

```text
lairen remove [OPTIONS] REF
```

Deletes the registry record and the stored credential blob. Deployed homes,
snapshots, and source homes are not touched.

| Option | Meaning |
|---|---|
| `--yes` | Confirm removal. Without it, the command refuses to proceed. |

```bash
lairen remove codex/alice@example.com --yes
```

## alias

```text
lairen alias [REF] [NAME] [--clear] [--json]
```

Manages stable short handles for accounts:

```bash
lairen alias 'kimi/u_123--d_456' kimi-1   # set or rename
lairen alias kimi-1                       # show one alias
lairen alias --json                       # list every alias
lairen alias kimi-1 --clear               # remove
```

| Argument or option | Meaning |
|---|---|
| `REF` | Account to inspect or update. Omit to list all aliases. |
| `NAME` | New alias. Omit with `REF` to show the current alias. |
| `--clear` | Remove the alias from `REF`. |
| `--json` | Emit `[{"ref", "alias"}]` when listing, or `{"ref", "alias"}` when showing one. |

Alias rules:

- Must start with a letter or digit; may contain letters, digits, `.`, `_`,
  `+`, `@`, and `-`; at most 64 characters; case-sensitive.
- Must be unique across aliases, account ids, and labels.
- Resolves before bare ids and labels. `provider/id` remains exact.
- Survives re-registration unless `register --alias` changes it.

## providers

```text
lairen providers
```

Prints a table of adapters:

```text
PROVIDER  TESTED  ENV  DEFAULT HOME  CREDENTIAL  NOTES
```

`TESTED` is `yes` only for adapters covered by live-credential tests. `ENV` is
the fallback environment variable, and `CREDENTIAL` is the path lairen reads
and writes relative to the provider home. See the
[provider reference](providers.md).

## doctor

```text
lairen doctor
```

Prints:

```text
config dir : <path>
data dir   : <path>
state dir  : <path>
accounts   : <count>
credentials: <count>
[<provider>] tested=<yes|no> home=<path> login=<yes|no>
```

`login=yes` means the provider's credential file exists in the resolved home.
`doctor` does not create directories or modify files.

## manual

```text
lairen manual [COMMAND]
```

An agent-oriented manual with concise topics and copyable examples. Running
`lairen manual` without a command prints the overview.

| Topic | Contents |
|---|---|
| `overview` | Mental model, core commands, and rules. |
| `commands` | Every command with synopsis and examples. |
| `workflows` | Task sequences for discovery, moves, swaps, and cleanup. |
| `providers` | Provider homes, credential paths, and identity rules. |
| `storage` | Registry, credential store, and snapshot layout. |
| `json` | Machine-readable output shapes and exit codes. |
| `safety` | Secret handling, rotation, and concurrency warnings. |
| `all` | Every topic in one document. |

Every topic accepts `--json`:

```bash
lairen manual workflows
lairen manual providers --json
lairen manual all --json
```

A topic's JSON output is `{"topic", "title", "text"}`. `all --json` adds the
installed version and nests the topics:

```json
{
  "version": "<installed version>",
  "topics": [{"topic": "overview", "title": "Overview", "text": "..."}]
}
```

Agents can load the whole guide with `lairen manual all` or parse the
structured form with `lairen manual all --json`.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success. |
| `1` | A lairen error: unknown or ambiguous ref, missing credential, refused removal, I/O failure, invalid registry or store JSON. The message is printed without a traceback. |
| `2` | Click usage error: unknown command, unknown option, missing argument, or an invalid choice or integer. |

lairen writes errors to stderr and normal output to stdout.
