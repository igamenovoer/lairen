# Local-Only Checkouts

Use `orphan/` for disposable clones, comparison checkouts, or research trees.
Everything except this README is ignored by Git. Project code, builds, tests,
and CI must not depend on entries here.

No local-only checkouts exist yet. Recreate an entry by cloning the upstream
repository into this directory; remove it with `rm -rf extern/orphan/<name>`.
