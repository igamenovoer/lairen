# Track usage and expiry

lairen reports local metadata from stored auth and from the live holder. It
does not query remote quota endpoints yet.

## Account overview

```bash
lairen account list
```

```text
REF                       ALIAS  LABEL              AUTH    HOLDER                            HOLDER STATE     DEPLOYED
codex/alice@example.com   aj     alice@example.com  stored  /home/me/codex-holders/codex-aj   ok              /home/me/code/project-a (link)
```

Columns:

- `AUTH`: `stored`, `missing`, or `none`
- `HOLDER`: holder home path or `-`
- `HOLDER STATE`: `ok`, `possibly-stale`, `missing`, `no-login`, or `none`
- `DEPLOYED`: active copy/link targets

Filters:

```bash
lairen account list --available
lairen account list --with-holder
lairen account list --stale-holders
lairen account list --provider codex
lairen account list --json
```

`--available` lists accounts with no active deployment. It replaces the old
top-level `available` command.

## One account

```bash
lairen account show aj
lairen account show aj --json
```

The JSON payload contains:

```json
{
  "ref": "codex/alice@example.com",
  "alias": "aj",
  "auth": {
    "stored": true,
    "present": true,
    "captured_at": "2026-11-12T04:00:00+00:00",
    "source_home": "/home/me/codex-holders/codex-aj",
    "usage": {"access_token_expires_at": 2000000000}
  },
  "holder": {
    "home": "/home/me/codex-holders/codex-aj",
    "state": "ok",
    "live": {
      "identity": {"id": "alice@example.com", "label": "alice@example.com"},
      "usage": {"access_token_expires_at": 2000000000}
    }
  },
  "deployments": []
}
```

The exact `holder` shape includes `recorded_at`, `verified_at`, `stale`, and a
`live` block when the holder is readable.

## Expiry table

```bash
lairen account usage
lairen account stats
lairen account usage aj --json
lairen account usage --json
```

```text
REF                       ACCESS EXPIRES (UTC)      REMAINING  HOLDER STATE
codex/alice@example.com   2026-11-25T12:00:00+00:00 in 13d0h    ok
```

If stored auth is missing, the record contains
`"error": "credential blob missing"`.

`expires_in_seconds` is negative after expiry. Expiry fields are null when the
credential has no expiry claim.

## Refresh stored auth

Stored auth does not follow a live home automatically. After a holder or a
deployed home refreshes:

```bash
lairen account sync aj
lairen account sync aj --holder-only
lairen account sync aj --home ~/code/project-b/.codex
lairen account sync aj --dry-run
```

`sync` chooses the freshest same-identity credential and updates the store. It
never changes the holder. When it reads the holder and the credential is
current, it clears a stale mark.

If a source now belongs to another identity, sync reports:

```text
warning: /path/.codex now belongs to codex/bob@example.com;
         run lairen account update codex/alice@example.com --home /path/.codex
```

## Strict checks

```bash
lairen status ~/code/project-b --strict
```

Strict mode fails for:

- unregistered account
- invalid credential
- drifted copy-source credential (`link` drift is informational)
- copy source with no stored auth
- stale holder
- missing holder
- holder with no login
- link that points outside the account holder

The error lists the account, reason, and a fix command.

## Machine-readable output

```bash
lairen account list --json
lairen account show aj --json
lairen account usage --json
lairen account sync --json
lairen status ~/code/project-b --json
lairen deploy list --json
lairen manual json
```

See `lairen manual json` for the current record shapes.
