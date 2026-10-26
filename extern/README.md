# External Project Layout

`lairen` keeps external, non-distribution material in this directory so it is
never confused with `src/` or treated as a runtime dependency.

| Path | Status | Purpose | Setup |
|---|---|---|---|
| `tracked/` | Tracked | Pinned third-party sources or Git submodules | See `tracked/README.md` |
| `orphan/` | Ignored | Local-only clones and disposable checkouts | See `orphan/README.md` |
| `trees/` | Ignored links | Views into persistent sibling Git worktrees | See `trees/README.md` |

Project code, builds, tests, and CI must not depend on `orphan/` or `trees/`.
`tracked/` is the only place where committed third-party source can live.
