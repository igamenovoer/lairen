# Installation

lairen is a pure Python package. It requires **Python 3.11 or newer**; the
development environment pins the 3.11 line.

## Recommended: uv

Install lairen as a uv tool so the `lairen` executable stays isolated from
other Python environments:

```bash
uv tool install lairen
lairen --version
```

Upgrade or remove it with:

```bash
uv tool upgrade lairen
uv tool uninstall lairen
```

## Run without installing

```bash
uvx lairen --help
```

`uvx` fetches the latest release, runs it, and leaves no permanent
installation. This is useful for a one-off scan or inspection.

## Add to a uv project

```bash
uv add lairen
uv run lairen --help
```

## Install from a source checkout

```bash
git clone https://github.com/igamenovoer/lairen.git
cd lairen
uv venv
uv pip install -e .
uv run lairen --help
```

## Develop with Pixi

The repository is a Pixi workspace. The Pixi environment contains Python 3.11,
the test and lint toolchain, and MkDocs Material for this documentation site.

```bash
git clone https://github.com/igamenovoer/lairen.git
cd lairen
pixi install
pixi run lairen --help
pixi run test
```

See [Contributing](../development/contributing.md) for the full task list.

## Other installers

If you do not use uv, pipx or pip work as well:

```bash
pipx install lairen
# or
python -m pip install --user lairen
```

Make sure the interpreter is Python 3.11 or newer.

## Verify the installation

```bash
lairen --version
lairen doctor
```

`lairen doctor` prints the resolved configuration, data, and state directories,
counts the saved accounts and credential blobs, and reports each provider's
home and login status. On a fresh machine it creates the lairen directories and
reports zero accounts.

## Where lairen keeps state

By default:

| Purpose | Location |
|---|---|
| Registry metadata | `${XDG_CONFIG_HOME:-~/.config}/lairen/registry.json` |
| Credential blobs | `${XDG_DATA_HOME:-~/.local/share}/lairen/credentials.json` |
| Pre-deploy snapshots | `~/.local/share/lairen/state/snapshots/` |

See [Storage and paths](../concepts/storage.md) for the full layout, the
`LAIREN_HOME` override, and file permissions.

## Next step

Continue with the [Quick start](quickstart.md) to register a real login and
deploy it into a project.
