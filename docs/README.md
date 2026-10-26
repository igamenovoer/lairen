# Documentation source

This directory is the MkDocs source for
<https://igamenovoer.github.io/lairen/>. The project README stays at the
repository root.

- Site configuration and navigation: `mkdocs.yml` at the repository root
- Live preview: `pixi run docs-serve` (serves `http://127.0.0.1:8000`)
- Strict build: `pixi run docs-build` (fails on warnings)

Every page belongs in the `nav` list in `mkdocs.yml`. This README is a
contributor note and is intentionally excluded from the build through the
`exclude_docs` setting.
