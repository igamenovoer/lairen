"""Shell-specific environment exports for holder activation."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from pathlib import Path

from lairen.errors import LairenError

SHELL_CHOICES = (
    "auto",
    "sh",
    "bash",
    "zsh",
    "fish",
    "csh",
    "tcsh",
    "powershell",
    "pwsh",
    "nu",
    "nushell",
)

_POSIX_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "ash"})
_CSH_SHELLS = frozenset({"csh", "tcsh"})
_POWERSHELL_SHELLS = frozenset({"powershell", "pwsh"})
_NU_SHELLS = frozenset({"nu", "nushell"})


def detect_shell(environ: Mapping[str, str] | None = None) -> str:
    """Return a supported shell name for the current process environment."""
    env = environ if environ is not None else os.environ
    shell = Path(env.get("SHELL", "")).name.lower()
    if shell in _POSIX_SHELLS:
        return shell
    if shell in _CSH_SHELLS:
        return shell
    if shell == "fish":
        return "fish"
    if shell in _POWERSHELL_SHELLS:
        return "powershell"
    if shell in _NU_SHELLS:
        return "nu"
    if env.get("PSModulePath"):
        return "powershell"
    return "sh"


def normalize_shell(name: str, environ: Mapping[str, str] | None = None) -> str:
    """Resolve ``auto`` and shell aliases into a supported shell name."""
    value = name.strip().lower()
    if value == "auto":
        return detect_shell(environ)
    if value in _POSIX_SHELLS:
        return value
    if value in _CSH_SHELLS:
        return value
    if value == "fish":
        return value
    if value in _POWERSHELL_SHELLS:
        return "powershell"
    if value in _NU_SHELLS:
        return "nu"
    raise LairenError(f"unsupported shell {name!r}; choose one of: {', '.join(SHELL_CHOICES)}")


def export_command(shell: str, name: str, value: str) -> str:
    """Return one command that exports ``name=value`` in ``shell``."""
    normalized = normalize_shell(shell)
    if normalized in _POSIX_SHELLS:
        return f"export {name}={shlex.quote(value)}"
    if normalized == "fish":
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"set -gx {name} '{escaped}'"
    if normalized in _CSH_SHELLS:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'setenv {name} "{escaped}"'
    if normalized == "powershell":
        escaped = value.replace("'", "''")
        return f"$env:{name} = '{escaped}'"
    escaped = value.replace("'", "''")
    return f"$env.{name} = '{escaped}'"
