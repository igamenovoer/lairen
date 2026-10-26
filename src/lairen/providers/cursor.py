"""Cursor desktop provider (SQLite ``state.vscdb``)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from lairen.errors import LairenError
from lairen.providers.base import Identity, Provider
from lairen.util import epoch_to_iso, normalize_epoch, parse_jwt_claims, sha256_hex

ACCESS_KEY = "cursorAuth/accessToken"
REFRESH_KEY = "cursorAuth/refreshToken"
EMAIL_KEY = "cursorAuth/cachedEmail"
AUTH_ID_KEY = "cursorAuth/authId"
MEMBERSHIP_KEY = "cursorAuth/stripeMembershipType"
SUBSCRIPTION_STATUS_KEY = "cursorAuth/stripeSubscriptionStatus"
SIGN_UP_TYPE_KEY = "cursorAuth/cachedSignUpType"
COMPAT_ACCESS_KEY = "cursor.accessToken"
COMPAT_EMAIL_KEY = "cursor.email"


class CursorProvider(Provider):
    name = "cursor"
    env_var = "CURSOR_HOME"
    tested = False
    deploy_note = "Desktop state.vscdb; close Cursor before deploying"
    DEFAULT_HOME = Path.home() / ".config" / "Cursor" / "User" / "globalStorage"
    CREDENTIAL_RELPATH = Path("state.vscdb")

    def default_home(self) -> Path:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ).expanduser()
        return base / "Cursor" / "User" / "globalStorage"

    @staticmethod
    def _read_item(conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?", (key,)
        ).fetchone()
        if not row or row[0] is None:
            return None
        value = row[0]
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        return value.strip() if value.strip() else None

    def read_live(self, home: Path) -> str:
        path = self.credential_path_for(home)
        if not path.is_file():
            raise LairenError(f"Cursor state database not found at {path}")
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                access_token = self._read_item(conn, ACCESS_KEY)
                refresh_token = self._read_item(conn, REFRESH_KEY)
                email = self._read_item(conn, EMAIL_KEY) or self._read_item(
                    conn, COMPAT_EMAIL_KEY
                )
                auth_id = self._read_item(conn, AUTH_ID_KEY)
                membership = self._read_item(conn, MEMBERSHIP_KEY)
                subscription = self._read_item(conn, SUBSCRIPTION_STATUS_KEY)
                sign_up = self._read_item(conn, SIGN_UP_TYPE_KEY)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise LairenError(f"cannot read Cursor state database {path}: {exc}") from exc

        if not access_token:
            raise LairenError("Cursor is not signed in (missing access token)")
        if not email:
            raise LairenError("Cursor credentials are missing cachedEmail")
        blob = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": email,
            "auth_id": auth_id or parse_jwt_claims(access_token).get("sub"),
            "membership_type": membership,
            "subscription_status": subscription,
            "sign_up_type": sign_up,
        }
        return json.dumps(blob)

    def parse_identity(self, home: Path, blob: str) -> Identity:
        data = self.load_json(blob)
        identity = data.get("email") or data.get("auth_id")
        if not identity:
            identity = f"cursor-{sha256_hex(blob.encode('utf-8'))}"
        return Identity(
            id=str(identity),
            label=str(data.get("email") or identity),
            extra={
                "email": data.get("email"),
                "auth_id": data.get("auth_id"),
                "membership_type": data.get("membership_type"),
            },
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        data = self.load_json(blob)
        claims = parse_jwt_claims(data.get("access_token"))
        expires_at = normalize_epoch(claims.get("exp"))
        return {
            "email": data.get("email"),
            "membership_type": data.get("membership_type"),
            "subscription_status": data.get("subscription_status"),
            "access_token_expires_at": expires_at,
            "access_token_expires_iso": epoch_to_iso(expires_at),
        }

    def deploy(self, home: Path, blob: str) -> Path:
        data = self.load_json(blob)
        path = self.credential_path_for(home)
        if not path.is_file():
            raise LairenError(
                f"Cursor state database not found at {path}; sign in to Cursor first"
            )
        values: dict[str, Any] = {
            ACCESS_KEY: data.get("access_token"),
            REFRESH_KEY: data.get("refresh_token"),
            EMAIL_KEY: data.get("email"),
            AUTH_ID_KEY: data.get("auth_id"),
            MEMBERSHIP_KEY: data.get("membership_type"),
            SUBSCRIPTION_STATUS_KEY: data.get("subscription_status"),
            SIGN_UP_TYPE_KEY: data.get("sign_up_type"),
            COMPAT_ACCESS_KEY: data.get("access_token"),
            COMPAT_EMAIL_KEY: data.get("email"),
        }
        try:
            conn = sqlite3.connect(path)
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS ItemTable "
                    "(key TEXT PRIMARY KEY, value TEXT)"
                )
                with conn:
                    for key, value in values.items():
                        if value is None:
                            conn.execute(
                                "DELETE FROM ItemTable WHERE key = ?", (key,)
                            )
                        else:
                            conn.execute(
                                "INSERT OR REPLACE INTO ItemTable (key, value) "
                                "VALUES (?, ?)",
                                (key, str(value)),
                            )
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise LairenError(
                f"cannot update Cursor state database {path}; close Cursor and retry: {exc}"
            ) from exc
        return path
