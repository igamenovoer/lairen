# Providers

lairen adapts to each CLI agent's own credential storage. A provider supplies:

- a default home and an optional environment-variable fallback;
- the credential path relative to the home;
- identity extraction and local usage metadata;
- provider-specific read, write, and merge behavior.

`TESTED=yes` means the adapter is exercised against live credentials in this
project. `TESTED=no` means the adapter implements the documented upstream
layout but has only been tested with synthetic payloads. `register` and
`deploy` print a warning when an experimental adapter is used.

## Summary

| Provider | Tested | Env fallback | Default home | Credential | Deploy behavior |
|---|---|---:|---|---|---|
| `claude` | no | `CLAUDE_CONFIG_DIR` | `~/.claude` | `.credentials.json` | Replaces credentials; merges `oauthAccount` into `.claude.json` |
| `codex` | yes | `CODEX_HOME` | `~/.codex` | `auth.json` | Replaces the file |
| `commandcode` | no | `COMMANDCODE_HOME` | `~/.commandcode` | `auth.json` | Writes `{"apiKey": "..."}` |
| `cursor` | no | `CURSOR_HOME` | `${XDG_CONFIG_HOME:-~/.config}/Cursor/User/globalStorage` | `state.vscdb` | Updates `ItemTable` rows in place |
| `kimi` | yes | `KIMI_CODE_HOME` | `~/.kimi-code` | `credentials/kimi-code.json` | Replaces the credential file |
| `opencode` | no | `OPENCODE_HOME` | `${XDG_DATA_HOME:-~/.local/share}/opencode` | `auth.json` | Replaces only the `opencode-go` slot |

Run `lairen providers` to print the same information from the installed
version.

## Home resolution

For `register`:

1. `--home PATH`
2. the provider environment variable
3. the provider default home

For `deploy`, `--home` is mandatory. See
[Storage and paths](../concepts/storage.md#provider-home-resolution).

## codex

**Tested.** Uses the ChatGPT OAuth login that Codex stores in `auth.json`.

- Home: `~/.codex` (`CODEX_HOME`)
- Credential: `auth.json`
- Saved blob: the file contents, unchanged
- Identity: `account_key`, else `id_token` email, else token `account_id`, else
  a SHA-256 hash
- Deploy: replaces `auth.json`
- Usage: email, account id, name, `last_refresh`, access-token expiry

Project-local layouts such as `<project>/.codex/auth.json` are discovered by
[scan](../guides/scanning.md).

## kimi

**Tested.** Uses Kimi Code session credentials.

- Home: `~/.kimi-code` (`KIMI_CODE_HOME`)
- Credential: `credentials/kimi-code.json`
- Saved blob: the selected credential file, unchanged
- Identity: `user_id--device_id`, falling back to `user_id`, then a hash
- Deploy: writes `credentials/kimi-code.json` in the target home
- Usage: user id, device id, scope, token type, access- and refresh-token expiry

Kimi identities are sessions, not accounts. Two logins of the same `user_id`
remain separately deployable because the device id is part of the ref. See
[Identities and refs](../concepts/identities.md#why-kimi-identities-include-device_id).

## claude

**Experimental.** Wraps Claude Code's credentials and account metadata.

- Home: `~/.claude` (`CLAUDE_CONFIG_DIR`)
- Credentials: `.credentials.json`
- Saved blob: `{"credentials": {...}, "oauth_account": {...}}`
- Identity: `oauthAccount.emailAddress`, else JWT email, else a hash
- Deploy: replaces `.credentials.json`; merges `oauthAccount` fields into
  `.claude.json`, preserving unrelated configuration
- Usage: email, scopes, access-token expiry

When the home is the global `~/.claude`, the account config is read from
`~/.claude.json`; for a custom home it is read from `<home>/.claude.json`.

## commandcode

**Experimental.** API-key authentication.

- Home: `~/.commandcode` (`COMMANDCODE_HOME`)
- Credential: `auth.json`
- Saved blob: `{"type": "api", "key": "..."}`
- Identity: `cc-<sha256 prefix>`
- Deploy: writes `{"apiKey": "<key>"}`
- Usage: key fingerprint only; no expiry

## cursor

**Experimental.** Cursor desktop stores auth in a SQLite database.

- Home: `${XDG_CONFIG_HOME:-~/.config}/Cursor/User/globalStorage`
  (`CURSOR_HOME`)
- Credential: `state.vscdb`
- Saved blob: a normalized JSON object with access token, refresh token, email,
  auth id, membership, subscription status, and sign-up type
- Identity: cached email, else auth id, else a hash
- Deploy: updates the `cursorAuth/*` and compatibility rows in `ItemTable`;
  other rows are preserved
- Usage: email, membership, subscription status, access-token expiry

The target `state.vscdb` must already exist. Close Cursor before deploying to
avoid a locked database.

## opencode

**Experimental.** Covers the `opencode-go` API-key slot only.

- Home: `${XDG_DATA_HOME:-~/.local/share}/opencode` (`OPENCODE_HOME`)
- Credential: `auth.json`
- Saved blob: `{"type": "api", "key": "..."}`
- Identity: `go-<sha256 prefix>`
- Deploy: preserves other slots in `auth.json` and replaces `opencode-go`
- Usage: key fingerprint only; no expiry

OpenCode Console accounts are metadata-only in the official client and are
switched with that client's own command. lairen does not manage them.

## Credential shapes

The store keeps each provider's blob as text:

| Provider | Stored text |
|---|---|
| `claude` | JSON wrapper with `credentials` and `oauth_account` |
| `codex` | Raw `auth.json` contents |
| `commandcode` | `{"type": "api", "key": "..."}` |
| `cursor` | Normalized JSON extracted from SQLite |
| `kimi` | Raw Kimi credential JSON |
| `opencode` | `{"type": "api", "key": "..."}` |

See [Storage and paths](../concepts/storage.md#credential-store-format) for the
store's outer format and permissions.

## Adding a provider

Adapters are subclasses of `lairen.providers.base.Provider`. See
[Contributing](../development/contributing.md#adding-a-provider).
