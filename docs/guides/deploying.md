# Deploy an account

`lairen deploy` has three modes. All three address an account by ref or alias.

| Mode | What it does | Requires |
|---|---|---|
| `copy` | Write stored auth into a project home | stored auth |
| `link` | Symlink a project home to the holder | holder home |
| `env` | Print a shell export for the holder | holder home + provider env var |

## Target resolution

`copy` and `link` share project target resolution:

- omit `--home` to use `<project>/<provider project home>`
- `--project` selects the project root; otherwise the current directory is used
- a relative `--home` resolves under `--project` or the current directory
- an absolute `--home` is used as-is
- Cursor has no default project home and requires `--home`

Project home names:

```text
codex        .codex
kimi         .kimi-code
claude       .claude
commandcode  .commandcode
opencode     .opencode
cursor       (none)
```

## Copy

```bash
lairen deploy copy aj --project ~/code/project-a
lairen deploy copy aj --home ~/code/project-a/.codex-2
lairen deploy copy aj --project ~/code/project-a --sync
```

`copy` writes the credential blob stored in lairen. It requires `account add`
(or `account sync`) to have captured auth first.

Before writing, lairen:

1. warns when the target looks like another provider's home
2. inspects an existing target credential
3. refuses to overwrite a newer credential for the same or another account
   unless `--force` is given
4. snapshots the existing target unless `--no-backup`

`--sync` first runs `account sync` for the account, then writes the refreshed
blob.

### Holder staleness

If the account has a holder and the copy target is not the holder, a successful
copy marks the holder `possibly-stale`:

```text
note: holder /home/me/codex-holders/codex-aj is now possibly stale;
      run `lairen account sync codex/alice@example.com
      --home /home/me/codex-holders/codex-aj` to refresh it
```

The mark is advisory. `link` and `env` still work and warn. `status --strict`
fails and prints the same remediation.

If the copy target is the holder home, lairen clears the stale mark instead and
notes that stored auth replaced the live holder.

## Link

```bash
lairen deploy link aj --project ~/code/project-a
lairen deploy link aj --project ~/code/project-a --home .codex-holder
```

`link` creates a symlink from the project home to the holder home. No credential
is copied. Sessions, caches, and refreshed tokens stay in the holder.

Rules:

- a symlink already pointing at the holder is a no-op
- a symlink to another target is replaced only with `--force`
- a real directory or file is never replaced; move it aside first
- a target equal to the holder home is rejected
- a stale holder warns on stderr but the link is created

Remove a link with:

```bash
lairen deploy unlink aj --project ~/code/project-a --yes
```

`unlink` removes only a symlink that points at the account's holder.

## Env

```bash
eval "$(lairen deploy env aj)"
```

For Bash/Zsh:

```text
export CODEX_HOME='/home/me/codex-holders/codex-aj'
```

Supported shells: `sh`, `bash`, `zsh`, `fish`, `csh`, `tcsh`, `powershell`,
`pwsh`, `nu`, and `nushell`. `auto` detects from `$SHELL` and defaults to
POSIX `sh`.

```bash
eval "$(lairen deploy env aj --shell fish)"
```

Only the export goes to stdout. Warnings (including a stale holder) go to
stderr, so `eval` is safe.

Cursor has no provider home environment variable; use `link` instead.

### tmux integration

`deploy env` can apply the holder env var inside tmux. This uses
[libtmux](https://github.com/tmux-python/libtmux) and is opt-in.

```bash
# Type the export into the current pane's shell
lairen deploy env aj --tmux

# Also set the session environment inherited by new panes
lairen deploy env aj --tmux --tmux-session

# Session only; safe when lairen is running under an agent
lairen deploy env aj --tmux-session

# Server global environment for future sessions
lairen deploy env aj --tmux-global
```

Options:

| Option | Meaning |
|---|---|
| `--tmux` | Type the export into the current pane's shell. |
| `--tmux-session` | Set the current session environment for new panes/windows. |
| `--tmux-global` | Set the tmux server global environment. |
| `--no-overwrite` | Refuse to replace a different session/global value. |
| `--no-print` | Suppress the shell export line; tmux reports still print. |

`--tmux` checks that lairen is the foreground process in the pane and that the
waiting process is a recognized shell. It refuses to type into a running
agent, editor, or pager. The typed export is queued on the pane's tty and runs
when the shell regains the prompt.

Session/global overwrites report both values:

```text
tmux session $1: CODEX_HOME=/old -> /new
```

Unchanged or newly set values report only the value:

```text
tmux session $1: CODEX_HOME=/new
```

`--no-overwrite` turns a different existing value into an error and changes
nothing. `--tmux-session` and `--tmux-global` are mutually exclusive.

## Staleness lifecycle

| Event | Holder state |
|---|---|
| `account add` | `ok` |
| `account set-home` | `ok` |
| `account update` | `ok` |
| `account sync` reading the holder | `ok` |
| `deploy copy` to another home | `possibly-stale` |
| `deploy copy` to the holder | `ok` |
| `deploy link` | unchanged |
| `deploy env` | unchanged |

Derived states also include `missing` (home is gone), `no-login` (home exists
without a credential), and `none` (no holder).

## Listing deployments

```bash
lairen deploy list
lairen deploy list --group-by project --active-only
lairen deploy list --mode link --json
lairen deploy list --account aj
```

The newest deployment for a `(provider, home)` pair is active. Older entries
are overwritten, including entries invalidated by an identity-changing
`account update`.

`deploy list` replaces the old `associations` command.
