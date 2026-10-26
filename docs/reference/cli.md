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
| [`list`](#list) | List saved accounts. |
| [`show`](#show) | Show one account and its local usage metadata. |
| [`deploy`](#deploy) | Write a saved credential into a target home. |
| [`scan`](#scan) | Discover Codex and Kimi credential homes. |
| [`usage`](#usage) | Show expiry and usage statistics. |
| [`remove`](#remove) | Remove an account and its stored credential. |
| [`providers`](#providers) | Show provider defaults and adapter status. |
| [`doctor`](#doctor) | Show resolved paths, counts, and provider homes. |
| [`manual`](#manual) | Agent-oriented usage manual with examples. |

Refs are `provider/id`, a unique bare id, or a unique label. See
[Identities and refs](../concepts/identities.md).

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

```bash
lairen register codex --home ~/code/project-a/.codex
lairen register kimi --home ~/kimi-homes/kimi-1 --label "kimi-lease-1"
```

Output:

```text
registered <ref>  label=<label>  source=<home>
```

Registering an existing `provider/id` replaces its metadata and blob.

For experimental providers, a warning is printed to stderr.

## list

```text
lairen list [--json]
```

Prints saved accounts, sorted by provider and id:

```text
REF  LABEL  SOURCE  LAST DEPLOYED
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

```bash
lairen deploy codex/alice@example.com --home ./project/.codex
```

Output:

```text
deployed <ref> -> <written credential path>
snapshot: <snapshot path>        # only when a target existed and backups are on
```

Updates `last_deployed_at` and `last_deployed_home` in the registry. See
[Deploy credentials](../guides/deploying.md) for target rules and merge
behavior.

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
