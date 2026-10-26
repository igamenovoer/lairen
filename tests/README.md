# Tests

Tests are split by ownership, not by framework:

- `core/` covers distributed code under `src/lairen/`.
- `aux/` covers repository-supporting content such as scripts, documentation,
  CI helpers, and development automation.

Each side has three categories:

- `unit/`: fast, deterministic checks of individual components.
- `integration/`: checks across components or their supported runtime boundary.
- `manual/`: checks that need a human or live credentials and are excluded from
  default CI collection.

Representative placement:

- Provider parsing and registry/store behavior: `core/unit/`.
- CLI flows with temporary homes: `core/integration/`.
- Repository layout and documentation checks: `aux/unit/`.
- Real Codex/Kimi credential experiments: `core/manual/`.

Run the suites from the project root:

```bash
pixi run test-core   # core unit + integration
pixi run test-aux    # aux unit + integration
pixi run test        # both suites
```

The default tasks pass explicit directories, so neither `manual/` tree is
collected by CI.
