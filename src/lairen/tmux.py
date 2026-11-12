"""tmux integration for holder environment activation."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from lairen.errors import LairenError
from lairen.shells import export_command, normalize_shell

SCOPE_SESSION = "session"
SCOPE_GLOBAL = "global"
_TMUX_SCOPES = (SCOPE_SESSION, SCOPE_GLOBAL)


class TmuxBackend(Protocol):
    """The tmux operations lairen needs, kept small for testability."""

    @property
    def pane_id(self) -> str: ...

    def scope_label(self, scope: str) -> str: ...

    def getenv(self, scope: str, name: str) -> str | None: ...

    def setenv(self, scope: str, name: str, value: str) -> None: ...

    def ensure_pane_target(self) -> str: ...

    def send_literal(self, command: str) -> None: ...


@dataclass(frozen=True)
class TmuxApplyResult:
    shell: str
    export_text: str
    lines: list[str]


class LibTmuxBackend:
    """Tmux backend implemented with libtmux."""

    def __init__(self, pane: Any):
        self._pane = pane

    @classmethod
    def from_env(cls) -> LibTmuxBackend:
        import libtmux.exc as tmux_exc
        from libtmux.pane import Pane

        try:
            pane = Pane.from_env()
        except tmux_exc.NotInsideTmux as exc:
            raise LairenError(
                "tmux integration requires a tmux session; "
                "TMUX/TMUX_PANE are not set"
            ) from exc
        except (tmux_exc.LibTmuxException, tmux_exc.TmuxObjectDoesNotExist) as exc:
            raise LairenError(f"cannot reach the current tmux pane: {exc}") from exc
        return cls(pane)

    @property
    def pane_id(self) -> str:
        return str(self._pane.pane_id)

    @property
    def session_id(self) -> str:
        return str(self._pane.session.session_id)

    def scope_label(self, scope: str) -> str:
        if scope == SCOPE_SESSION:
            return f"tmux session {self.session_id}"
        if scope == SCOPE_GLOBAL:
            return "tmux global"
        raise LairenError(f"unknown tmux scope: {scope}")

    def _target(self, scope: str) -> Any:
        if scope == SCOPE_SESSION:
            return self._pane.session
        if scope == SCOPE_GLOBAL:
            return self._pane.server
        raise LairenError(f"unknown tmux scope: {scope}")

    def getenv(self, scope: str, name: str) -> str | None:
        import libtmux.exc as tmux_exc

        try:
            value = self._target(scope).getenv(name)
        except (ValueError, tmux_exc.LibTmuxException) as exc:
            raise LairenError(
                f"cannot read {name} from {self.scope_label(scope)}: {exc}"
            ) from exc
        return value if isinstance(value, str) else None

    def setenv(self, scope: str, name: str, value: str) -> None:
        import libtmux.exc as tmux_exc

        try:
            self._target(scope).set_environment(name, value)
        except (ValueError, tmux_exc.LibTmuxException) as exc:
            raise LairenError(
                f"cannot set {name} in {self.scope_label(scope)}: {exc}"
            ) from exc

    def ensure_pane_target(self) -> str:
        foreground = self._foreground_pgrp()
        if foreground != os.getpgrp():
            raise LairenError(
                "--tmux requires lairen to be the foreground process in the "
                "current tmux pane; use --tmux-session for session-only injection"
            )
        shell = _parent_shell()
        if shell is None:
            raise LairenError(
                "cannot identify the shell behind the current tmux pane; "
                "run from an interactive shell or pass --shell"
            )
        return shell

    def send_literal(self, command: str) -> None:
        import libtmux.exc as tmux_exc

        try:
            self._pane.send_keys(command, literal=True, enter=True)
        except (ValueError, tmux_exc.LibTmuxException) as exc:
            raise LairenError(
                f"cannot send the export to the tmux pane: {exc}"
            ) from exc

    def _foreground_pgrp(self) -> int | None:
        for fd in (0, 1, 2):
            try:
                return os.tcgetpgrp(fd)
            except OSError:
                continue

        pane_tty = getattr(self._pane, "pane_tty", None)
        if not pane_tty:
            return None
        try:
            fd = os.open(pane_tty, os.O_RDONLY | getattr(os, "O_NOCTTY", 0))
        except OSError:
            return None
        try:
            return os.tcgetpgrp(fd)
        except OSError:
            return None
        finally:
            os.close(fd)


def apply_tmux_env(
    backend: TmuxBackend,
    env_var: str,
    value: str,
    *,
    inject_pane: bool,
    scope: str | None,
    no_overwrite: bool,
    shell_override: str | None = None,
) -> TmuxApplyResult:
    """Apply a holder env var to tmux scopes and optionally the current pane."""
    if scope is not None and scope not in _TMUX_SCOPES:
        raise LairenError(f"unknown tmux scope: {scope}")
    if no_overwrite and scope is None:
        raise LairenError(
            "--no-overwrite requires --tmux-session or --tmux-global; "
            "the current pane's live environment cannot be inspected portably"
        )

    detected_shell: str | None = None
    if inject_pane:
        detected_shell = backend.ensure_pane_target()

    requested_shell = (
        shell_override
        if shell_override not in (None, "auto")
        else detected_shell
    )
    if requested_shell is None:
        requested_shell = "auto"
    shell = normalize_shell(requested_shell)
    export_text = export_command(shell, env_var, value)

    lines: list[str] = []
    if scope is not None:
        old_value = backend.getenv(scope, env_var)
        if old_value is not None and old_value != value and no_overwrite:
            raise LairenError(
                f"{backend.scope_label(scope)} already sets {env_var} to "
                f"{old_value}; remove --no-overwrite to replace it"
            )
        if old_value != value:
            backend.setenv(scope, env_var, value)
            verified = backend.getenv(scope, env_var)
            if verified != value:
                raise LairenError(
                    f"{backend.scope_label(scope)}: failed to set {env_var}"
                )
        if old_value is not None and old_value != value:
            lines.append(
                f"{backend.scope_label(scope)}: {env_var}={old_value} -> {value}"
            )
        else:
            lines.append(f"{backend.scope_label(scope)}: {env_var}={value}")

    if inject_pane:
        backend.send_literal(export_text)
        lines.append(f"tmux pane {backend.pane_id}: {env_var}={value}")

    return TmuxApplyResult(shell=shell, export_text=export_text, lines=lines)


def _parent_shell() -> str | None:
    command = _process_command(os.getppid())
    if not command:
        return None
    name = Path(command.split()[0]).name.lstrip("-").lower()
    try:
        return normalize_shell(name)
    except LairenError:
        return None


def _process_command(pid: int) -> str | None:
    proc = Path(f"/proc/{pid}/comm")
    try:
        if proc.is_file():
            value = proc.read_text(encoding="utf-8").strip()
            if value:
                return value
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None
