# Persistent Worktree Views

`trees/` holds ignored symlinks to persistent sibling Git worktrees. Each link
is a convenience view, not vendored code, a submodule, or a runtime dependency.
Temporary in-repo worktrees must not be exposed here.

No linked worktrees exist yet. Create a link with a stable relative path,
verify it with `readlink` and `realpath`, and record the logical name and
branch here. Remove a link with `rm extern/trees/<name>` after confirming it
points at the intended worktree.
