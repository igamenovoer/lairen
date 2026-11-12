# Identities and refs

An account is a unique credential identity accepted by a provider CLI. The
identity is provider-specific and stable for that credential.

## Account ids

| Provider | Identity |
|---|---|
| `codex` | `account_key`, else id-token email, else `account_id` |
| `kimi` | `user_id--device_id` |
| `claude` | `emailAddress` from `oauthAccount`, else JWT email |
| `commandcode` | `cc-<sha256 prefix>` of the API key |
| `opencode` | `go-<sha256 prefix>` of the API key |
| `cursor` | cached email, else `auth_id` |

Kimi identities include the device session. Two logins of the same user are
different accounts and deploy independently:

```text
kimi/user-123--device-456
kimi/user-123--device-789
```

## Refs

A ref is `provider/id`:

```text
codex/alice@example.com
kimi/user-123--device-456
```

Commands also accept, in order:

1. a unique alias
2. a unique bare id
3. a unique label

```bash
lairen account alias codex/alice@example.com aj
lairen account show aj
lairen deploy copy aj --project ~/code/project
```

Aliases are unique, survive re-registration and `account update`, and are
managed with `lairen account alias`.

## Auth and holder are not identity

An account can exist with:

- stored auth only
- a holder home only
- both
- neither (identity metadata only)

The holder is one live home attached to the account. It does not change the
identity and cannot point at a different account. `account set-home` rejects a
home whose live credential belongs to another identity; use `account update`
when the identity itself changes.

## Identity changes

`account update` reads a new home. If the derived identity differs from the
current one:

- the ref changes
- the alias survives
- the old credential blob is removed
- the new home becomes the holder
- `--keep-home` is rejected

```bash
lairen account update aj --home ~/kimi-homes/kimi-2064-2
```

The alias continues to resolve to the updated account.

## One holder per account

An account has at most one holder home. If an identity has multiple live homes,
choose one as the holder and treat the others as deployed copies or ordinary
provider homes. Use `account set-home` to switch.

## Kimi session note

A Kimi credential file is a session, not just a user. Refreshing one session
does not refresh another. This is why the device id is part of the account id
and why `lairen account usage` reports each session separately.
