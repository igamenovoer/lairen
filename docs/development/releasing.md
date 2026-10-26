# Releasing

lairen publishes to PyPI through GitHub Actions trusted publishing and publishes
this site to GitHub Pages on every push to `main`.

## Version locations

Update the version in both places before tagging:

- `pyproject.toml`: `[project] version`
- `src/lairen/__init__.py`: `__version__`

Also update any version mention in `README.md` (the status line) and check that
the examples in `docs/` still describe the released behavior.

## Pre-release checks

```bash
pixi run test
pixi run lint
pixi run typecheck
pixi run docs-build
pixi run build
```

`docs-build` runs with `--strict`; warnings fail the build. The site is copied
to `site/`, which is not committed.

## Publish a release

1. Commit the version bump and merge it to `main`.
2. Create and push an annotated tag:

   ```bash
   git tag -a vX.Y.Z -m "lairen X.Y.Z"
   git push origin vX.Y.Z
   ```

3. Create the GitHub release. Publishing the release triggers the PyPI
   workflow:

   ```bash
   gh release create vX.Y.Z --title "lairen X.Y.Z" --generate-notes
   ```

4. Watch the workflow:

   ```bash
   gh run list --workflow workflow.yml
   gh run watch <run-id>
   ```

## How publishing is wired

- `.github/workflows/workflow.yml` runs on `release: published` and on manual
  dispatch. It builds the distributions with Pixi and uploads them with
  `pypa/gh-action-pypi-publish`.
- The PyPI project uses a **pending trusted publisher** for
  `igamenovoer/lairen`, workflow file `workflow.yml`, no environment
  restriction. The workflow filename must stay `workflow.yml`.
- No PyPI token is stored in the repository. The job authenticates with
  `id-token: write`.

## Verify the release

```bash
uvx --from 'lairen==X.Y.Z' lairen --version
```

Check the PyPI project page and the generated metadata:

```bash
curl -s https://pypi.org/pypi/lairen/json | python -c \
  "import json,sys; d=json.load(sys.stdin); print(d['info']['version'])"
```

PyPI embeds the README from the uploaded artifacts. A README-only change is
visible on the project page only after the next release.

## Documentation deployment

`.github/workflows/docs.yml` builds `mkdocs.yml` with `pixi run docs-build` and
deploys `site/` through GitHub Pages. It runs on pushes to `main` that touch
docs inputs and can be started manually.

Pages is configured with **Source: GitHub Actions** for this repository. The
site URL is:

```text
https://igamenovoer.github.io/lairen/
```

Verify a deployment with:

```bash
gh run list --workflow docs.yml
curl -sI https://igamenovoer.github.io/lairen/ | head
```

The deploy job uses the `github-pages` environment. Deployment history is
available under the repository's **Actions** and **Deployments** tabs.
