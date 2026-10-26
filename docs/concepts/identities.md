# Identities and refs

Every saved login is an **account**: one provider plus one stable account id.
Accounts are addressed by a **ref** of the form `provider/id`.

```text
codex/alice@example.com
kimi/u_123--d_456
```

Refs are what `show`, `deploy`, `usage`, `remove`, and `alias` accept. The
registry stores the provider and id separately and derives the ref from them.

## How refs resolve

When a command receives a ref, lairen resolves it in this order:

1. **Explicit form** `provider/id`: matches the provider and id exactly.
2. **Alias**: matches the account's unique alias.
3. **Bare id**: matches any account whose id equals the argument.
4. **Label**: matches any account whose label equals the argument.

Any of these forms is accepted by `show`, `deploy`, `usage`, `remove`, and the
alias and manual commands that take a ref. The short forms succeed only when
exactly one account matches. If several accounts share the token, lairen stops
with an ambiguity error and lists the full refs:

```text
Error: ambiguous account 'alice'; use one of: codex/alice@example.com, kimi/alice
```

Use the full `provider/id` when in doubt.

## Aliases

An alias is a stable, user-chosen handle for an account. It exists so long Kimi
session refs and repeated project paths do not have to be retyped:

```bash
lairen alias 'kimi/u_123--d_456' kimi-1
lairen deploy kimi-1 --home ~/code/project/.kimi-code
```

Manage aliases with the same command:

```bash
lairen alias kimi-1              # show the alias for an account
lairen alias --json              # list every alias
lairen alias kimi-1 --clear      # remove it
```

Rules:

- An alias must start with a letter or digit and may contain letters, digits,
  `.`, `_`, `+`, `@`, and `-`. It is at most 64 characters, is case-sensitive,
  and cannot contain `/` or whitespace.
- An alias must be unique. It is rejected if it equals another account's alias,
  id, or label.
- Aliases take precedence over bare ids and labels during resolution. The
  explicit `provider/id` form is always exact and unaffected.
- Re-registering an account with `register` or `scan --register` preserves its
  alias. `register --alias NAME` sets or replaces it.
- The alias is stored in the registry as the optional `alias` field. It is not
  secret and does not affect credential storage.

## Updating an account

`lairen update REF --home PATH` replaces a stored credential from a new
provider home without losing the account's identity metadata:

```bash
lairen update kimi-2064-1 --home ~/kimi-homes/kimi-2064-1
```

- If the new credential has the same identity, the ref is unchanged and the
  blob, source home, and provider metadata are refreshed.
- If the identity changed, the account id and ref follow the new credential.
  The alias stays attached, a provider-derived label follows the new identity,
  and a custom label is preserved. The old credential blob is removed.
- If the new identity already belongs to a different account, lairen refuses to
  merge the two. Remove or update the other account first.
- `created_at` and deployment history are preserved. Existing deployed homes
  are not rewritten; deploy again to push the new credential to them.

## Project leases

`lairen status [DIRECTORY]` reads the project's live `.codex` and `.kimi-code`
homes, matches each credential to the registry, and reports its state:
`current`, `drifted`, `unregistered`, `invalid`, `missing-store-blob`, or
`no-login`.

Its `OTHER PROJECTS` column comes from the append-only
[deployment log](storage.md#deployment-log), so `deploy`, `update`, and
`remove` history is visible per account. Accounts deployed before the log
existed fall back to `last_deployed_home` and are marked `(last deploy)`.

## Labels

Labels are display names. They are not unique, and changing a label never
changes the stored id. `register --label NAME` sets a label at registration
time; the default label comes from the provider's identity extraction. Labels
remain useful for `list` output and for resolution when no alias exists.

## How each provider derives an id

lairen decodes JWT payloads without verifying signatures. Identity extraction
is local bookkeeping, not authentication. Every fallback is deterministic, so
re-registering the same blob produces the same id.

| Provider | Account id | Notes |
|---|---|---|
| `codex` | `account_key`, else `email`, else token `account_id` | Email and name come from the `id_token` claims when present. |
| `kimi` | `user_id--device_id` | Falls back to `user_id`, then to a content hash. |
| `claude` | `emailAddress` from `oauthAccount`, else JWT email | The saved blob wraps credentials plus `oauthAccount` metadata. |
| `commandcode` | `cc-<sha256 prefix of API key>` | API-key auth; the label shows the last four characters. |
| `cursor` | cached email, else `auth_id` | The label is the email when available. |
| `opencode` | `go-<sha256 prefix of API key>` | Covers the `opencode-go` API-key slot only. |

If a credential cannot yield any identity field, lairen derives an id from a
SHA-256 hash of the blob, for example `codex-3f2a1c9d0b11`. The account is still
usable, but the id is opaque and changes if the blob changes.

## Why Kimi identities include `device_id`

Kimi Code logins are sessions: a `user_id` plus a `device_id`. One human
account can hold several independent sessions, for example one per lease or per
machine. Keying only by `user_id` would collapse those sessions into one slot
and make them impossible to deploy independently.

lairen therefore stores the session key:

```text
kimi/u_123--d_456
      └────┬──┘  └─┬─┘
        user_id   device_id
```

Two logins of the same user remain distinct accounts:

```text
kimi/u_123--d_456
kimi/u_123--d_789
```

The default label is the bare `user_id`, so both rows look similar in
`lairen list`. Pass `--label` when registering leases if you need to tell them
apart at a glance.

## Registry versus credential store

The two halves of an account are stored separately:

- The **registry** holds metadata: provider, id, label, source home, creation
  time, last deployment, and non-secret extras such as email or device id.
- The **credential store** holds the credential blob, keyed by
  `provider:id`.

`lairen list` and `lairen usage` read only the registry and credential
metadata. Removing an account deletes both halves; losing one half leaves the
other orphaned, and `lairen show` reports a missing blob explicitly.

See [Storage and paths](storage.md) for the on-disk files and
[Providers](../reference/providers.md) for the per-provider credential shapes.
