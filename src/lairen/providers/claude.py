"""Claude Code provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lairen.errors import LairenError
from lairen.providers.base import Identity, Provider
from lairen.util import atomic_write_text, epoch_to_iso, normalize_epoch, parse_jwt_claims


class ClaudeProvider(Provider):
    name = "claude"
    env_var = "CLAUDE_CONFIG_DIR"
    tested = False
    deploy_note = "OAuth credentials; oauthAccount metadata is merged on deploy"
    DEFAULT_HOME = Path.home() / ".claude"
    CREDENTIAL_RELPATH = Path(".credentials.json")

    def _global_config_path(self, home: Path) -> Path:
        if home.name == ".claude" and home.parent == Path.home():
            return home.parent / ".claude.json"
        return home / ".claude.json"

    def _read_global_config(self, home: Path) -> dict[str, Any]:
        path = self._global_config_path(home)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def read_live(self, home: Path) -> str:
        credentials = self.load_json(super().read_live(home))
        config = self._read_global_config(home)
        payload = {
            "credentials": credentials,
            "oauth_account": config.get("oauthAccount"),
        }
        return json.dumps(payload, ensure_ascii=False)

    def parse_identity(self, home: Path, blob: str) -> Identity:
        data = self.load_json(blob)
        oauth_raw = data.get("oauth_account")
        oauth: dict[str, Any] = oauth_raw if isinstance(oauth_raw, dict) else {}
        email = oauth.get("emailAddress")
        if not email:
            credentials = data.get("credentials") or {}
            inner = credentials.get("claudeAiOauth") or {}
            claims = parse_jwt_claims(inner.get("accessToken"))
            email = claims.get("email")
        if not email:
            digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
            email = f"claude-{digest}"
        return Identity(
            id=str(email),
            label=str(email),
            extra={
                "email": email,
                "account_uuid": oauth.get("accountUuid"),
                "organization_uuid": oauth.get("organizationUuid"),
                "organization_name": oauth.get("organizationName"),
            },
        )

    def local_usage(self, blob: str) -> dict[str, object]:
        data = self.load_json(blob)
        credentials = data.get("credentials") or {}
        oauth = credentials.get("claudeAiOauth") or {}
        oauth_account_raw = data.get("oauth_account")
        oauth_account: dict[str, Any] = (
            oauth_account_raw if isinstance(oauth_account_raw, dict) else {}
        )
        expires_at = normalize_epoch(oauth.get("expiresAt"))
        return {
            "email": oauth_account.get("emailAddress"),
            "scopes": oauth.get("scopes"),
            "access_token_expires_at": expires_at,
            "access_token_expires_iso": epoch_to_iso(expires_at),
        }

    def write_live(self, home: Path, blob: str) -> Path:
        data = self.load_json(blob)
        credentials = data.get("credentials")
        if not isinstance(credentials, dict):
            raise LairenError("claude blob is missing credentials")
        path = self.credential_path_for(home)
        atomic_write_text(
            path,
            json.dumps(credentials, indent=2, ensure_ascii=False) + "\n",
            mode=0o600,
        )

        oauth = data.get("oauth_account")
        if isinstance(oauth, dict) and oauth:
            config_path = self._global_config_path(home)
            config: dict[str, Any] = {}
            if config_path.is_file():
                try:
                    loaded = json.loads(config_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        config = loaded
                except (OSError, json.JSONDecodeError):
                    config = {}
            existing = config.get("oauthAccount")
            merged = dict(existing) if isinstance(existing, dict) else {}
            for key, value in oauth.items():
                if value is not None:
                    merged[key] = value
            config["oauthAccount"] = merged
            atomic_write_text(
                config_path,
                json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                mode=0o600,
            )
        return path
