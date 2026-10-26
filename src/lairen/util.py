"""Small shared helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_hex(data: bytes, length: int = 16) -> str:
    return hashlib.sha256(data).hexdigest()[:length]


def normalize_epoch(value: Any) -> int | None:
    """Return epoch seconds, accepting millisecond timestamps."""
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        number //= 1000
    return number



def parse_jwt_claims(token: str | None) -> dict[str, Any]:
    """Decode a JWT payload without verification. Returns {} on any failure."""
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def epoch_to_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError, OSError):
        return None


def format_remaining(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds <= 0:
        return f"expired {format_duration(-seconds)} ago"
    return f"in {format_duration(seconds)}"


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes}m"
    if minutes:
        return f"{minutes}m{secs}s"
    return f"{secs}s"


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    """Write text through a temporary file and rename it into place."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
