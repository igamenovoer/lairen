# Contributing

lairen is developed as a Pixi workspace. The Pixi environment provides Python
3.11, the package in editable mode, the test and lint toolchain, and MkDocs
Material for the documentation site.

## Setup

```bash
git clone https://github.com/igamenovoer/lairen.git
cd lairen
pixi install
pixi run lairen --help
pixi run test
```

CI uses Pixi `0.81.0`; a recent Pixi release is recommended.

## Tasks

| Task | Purpose |
|---|---|
| `pixi run test` | Run both suites. |
| `pixi run test-core` | Unit and integration tests for `src/lairen/`. |
| `pixi run test-aux` | Tests for repository support files. |
| `pixi run lint` | Run Ruff over `src/` and `tests/`. |
| `pixi run fmt` | Format `src/` and `tests/` with Ruff. |
| `pixi run typecheck` | Run mypy over `src/`. |
| `pixi run build` | Build the sdist and wheel. |
| `pixi run docs-serve` | Serve this site at `http://127.0.0.1:8000`. |
| `pixi run docs-build` | Build the site with `--strict`. |

`docs-build` fails on broken links, missing nav entries, and other warnings.
Run it before opening a documentation pull request.

## Layout

| Path | Contents |
|---|---|
| `src/lairen/` | Importable package and Click CLI. |
| `tests/core/` | Tests for distributed code. |
| `tests/aux/` | Tests for repository support content, including layout checks. |
| `docs/` | Markdown source for this site. |
| `mkdocs.yml` | Site configuration and navigation. |
| `context/` | Plans, feature notes, design notes, and summaries. |
| `scripts/` | Repository automation outside the installed package. |
| `skillset/` | Project-specific agent skills. |

Tests are split by ownership, not framework:

- `unit/`: fast, deterministic checks of individual components.
- `integration/`: checks across components or the supported runtime boundary.
- `manual/`: checks that need a human or live credentials. These are excluded
  from the default Pixi tasks and from CI.

Place tests for distributed code under `tests/core/`. Place tests for
repository support such as docs or scripts under `tests/aux/`.

## Style

- Python `>=3.11`; the environment pins the 3.11 line.
- Use absolute imports only. Do not use relative imports in `src/` or `tests/`.
- Ruff line length is 100 with the `E`, `F`, `I`, `UP`, and `B` rules.
- mypy checks `src/`.
- Keep provider logic inside `src/lairen/providers/`; the CLI and store should
  stay provider-agnostic.

## Adding a provider

1. Add `src/lairen/providers/<name>.py` with a `Provider` subclass.
2. Set `name`, `env_var`, `DEFAULT_HOME`, and `CREDENTIAL_RELPATH`.
3. Implement `parse_identity()` and `local_usage()`.
4. Override `read_live()`, `write_live()`, `compose()`, or `deploy()` when the
   upstream layout is not a single JSON file.
5. Leave `tested = False` until live-credential tests exist, and set a short
   `deploy_note` describing the limitation.
6. Register the adapter in `src/lairen/providers/__init__.py`.
7. Document it in `docs/reference/providers.md` and update the summary table.

Auto-discovery is deliberately limited to Codex and Kimi. A new provider can be
registered by explicit `--home`, even if `lairen scan` does not search for it.
Adding scan support means extending `src/lairen/scan.py` and its tests.

## Documentation

The site is built with MkDocs Material:

```bash
pixi run docs-serve     # live reload at http://127.0.0.1:8000
pixi run docs-build     # strict build into site/
```

Guidelines:

- Put pages under `docs/` and add every page to the `nav` in `mkdocs.yml`.
  `docs/README.md` is a contributor note and is intentionally excluded with
  `exclude_docs`.
- Use relative links between pages and run `docs-build` to catch broken links.
- Keep commands and output blocks consistent with the current CLI. If you
  change a command's help text or output, update `docs/reference/cli.md`.
- Do not paste real tokens, account keys, or private home paths into examples.

## Tests and CI

The CI workflow runs `pixi run test`, `pixi run lint`, `pixi run typecheck`, and
`pixi run docs-build` on every push and pull request. All four must pass.

Live-credential experiments belong in `tests/core/manual/` and must not run in
CI.
