# Track usage and expiry

`lairen usage` reports what lairen can know locally about each saved account:
token expiry, refresh expiry where available, account identifiers, and the last
deployment. It does not contact provider APIs.

```bash
lairen usage [REFS]... [--json]
```

With no refs, every saved account is included. With refs, only those accounts
are reported. `stats` is an alias for `usage`.

## Table output

```bash
lairen usage
```

```text
REF                          ACCESS EXPIRES (UTC)       REMAINING  LAST DEPLOYED
codex/alice@example.com      2026-11-25T12:00:00+00:00  in 30d0h   2026-10-26T12:00:00+00:00
kimi/u_123--d_456            2026-11-01T08:30:00+00:00  in 6d20h   -
```

`REMAINING` is computed when the command runs:

- `in 30d0h`, `in 6h4m`, `in 12m3s`: the access token is still valid.
- `expired 2h10m ago`: the stored token has expired.
- `-`: no expiry claim could be extracted.

`LAST DEPLOYED` comes from the registry and is `-` for an account that has
never been deployed.

## JSON output

```bash
lairen usage --json
lairen usage codex/alice@example.com --json
```

```json
[
  {
    "ref": "codex/alice@example.com",
    "provider": "codex",
    "label": "alice@example.com",
    "last_deployed_at": "2026-10-26T12:00:00+00:00",
    "expires_at": "2026-11-25T12:00:00+00:00",
    "expires_in_seconds": 2592000,
    "expires_in": "in 30d0h",
    "usage": {
      "email": "alice@example.com",
      "account_id": "acct_123",
      "name": "Alice",
      "last_refresh": "2026-10-26T11:55:00+00:00",
      "access_token_expires_at": 1795608000,
      "access_token_expires_iso": "2026-11-25T12:00:00+00:00"
    }
  }
]
```

Fields at the top level are always present. If the credential blob is missing
from the store, the record contains an `error` field instead of expiry and
usage fields.

`expires_in_seconds` is negative after expiry. `expires_at` and
`expires_in` are `null` when no expiry claim exists.

## Per-provider usage metadata

The `usage` object is provider-specific:

| Provider | Fields |
|---|---|
| `codex` | `email`, `account_id`, `name`, `last_refresh`, `access_token_expires_at`, `access_token_expires_iso` |
| `kimi` | `user_id`, `device_id`, `scope`, `token_type`, `access_token_expires_at`, `access_token_expires_iso`, `refresh_token_expires_at`, `refresh_token_expires_iso` |
| `claude` | `email`, `scopes`, `access_token_expires_at`, `access_token_expires_iso` |
| `commandcode` | `kind`, `fingerprint` (no expiry) |
| `cursor` | `email`, `membership_type`, `subscription_status`, `access_token_expires_at`, `access_token_expires_iso` |
| `opencode` | `kind`, `fingerprint` (no expiry) |

API-key providers have no token expiry, so their `ACCESS EXPIRES` column is
`-`.

## Show one account

`lairen show` returns the account record and usage metadata as a JSON object:

```bash
lairen show codex/alice@example.com
```

```json
{
  "account": {
    "provider": "codex",
    "id": "alice@example.com",
    "label": "alice@example.com",
    "source_home": "/home/alice/code/project-a/.codex",
    "created_at": "2026-10-26T12:00:00+00:00",
    "last_deployed_at": "2026-10-26T12:00:00+00:00",
    "last_deployed_home": "/home/alice/code/project-b/.codex",
    "extra": {
      "email": "alice@example.com",
      "account_id": "acct_123",
      "name": "Alice"
    }
  },
  "usage": {
    "email": "alice@example.com",
    "account_id": "acct_123",
    "name": "Alice",
    "last_refresh": "2026-10-26T11:55:00+00:00",
    "access_token_expires_at": 1795608000,
    "access_token_expires_iso": "2026-11-25T12:00:00+00:00"
  }
}
```

If the registry record exists but the credential blob is missing, `show` exits
with an error: `credential blob missing for codex/alice@example.com`.

## Why expiry can be stale

lairen reports the token that was saved at registration time. When a deployed
agent refreshes its session, the provider may issue a new access token and a
new refresh token, and the client writes them into the live home. The stored
blob does not change.

To refresh lairen's view:

```bash
lairen register codex --home ~/code/project-b/.codex
```

Re-registering updates the existing `provider/id` record with the new blob.

Remote quota endpoints, account balances, and live rate-limit state are not
implemented. `Provider.local_usage()` is the extension point for a future
remote query, but everything documented here is derived from stored
credentials and registry metadata.
