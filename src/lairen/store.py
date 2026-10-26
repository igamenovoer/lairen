"""Registry metadata and credential blob storage."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import LairenError
from .models import Account
from .util import atomic_write_text


class Registry:
    """Account metadata, stored as a JSON list."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[Account]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LairenError(f"cannot read registry {self.path}: {exc}") from exc
        if not isinstance(data, list):
            raise LairenError(f"registry {self.path} is not a JSON list")
        return [Account.from_dict(item) for item in data]

    def save(self, accounts: list[Account]) -> None:
        payload = json.dumps(
            [account.to_dict() for account in accounts], indent=2, ensure_ascii=False
        )
        atomic_write_text(self.path, payload + "\n", mode=0o600)

    def upsert(self, account: Account) -> Account:
        accounts = self.load()
        for index, existing in enumerate(accounts):
            if existing.provider == account.provider and existing.id == account.id:
                accounts[index] = account
                break
        else:
            accounts.append(account)
        self.save(accounts)
        return account

    def list(self) -> list[Account]:
        return sorted(self.load(), key=lambda item: (item.provider, item.id))

    def get(self, provider: str, account_id: str) -> Account | None:
        for account in self.load():
            if account.provider == provider and account.id == account_id:
                return account
        return None

    def resolve(self, ref: str) -> Account:
        accounts = self.load()
        if "/" in ref:
            provider, _, account_id = ref.partition("/")
            for account in accounts:
                if account.provider == provider and account.id == account_id:
                    return account
            raise LairenError(f"unknown account: {ref}")

        matches = [
            account
            for account in accounts
            if account.id == ref or account.label == ref
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LairenError(f"unknown account: {ref}")
        refs = ", ".join(account.ref for account in matches)
        raise LairenError(f"ambiguous account {ref!r}; use one of: {refs}")

    def remove(self, provider: str, account_id: str) -> bool:
        accounts = self.load()
        kept = [
            account
            for account in accounts
            if not (account.provider == provider and account.id == account_id)
        ]
        if len(kept) == len(accounts):
            return False
        self.save(kept)
        return True


class CredentialStore:
    """Credential blobs, keyed by <provider>:<account-id>."""

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _key(provider: str, account_id: str) -> str:
        return f"{provider}:{account_id}"

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LairenError(f"cannot read credentials {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise LairenError(f"credential store {self.path} is not a JSON object")
        return {str(key): str(value) for key, value in data.items()}

    def _save(self, data: dict[str, str]) -> None:
        atomic_write_text(
            self.path,
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            mode=0o600,
        )

    def get(self, provider: str, account_id: str) -> str | None:
        return self._load().get(self._key(provider, account_id))

    def set(self, provider: str, account_id: str, blob: str) -> None:
        data = self._load()
        data[self._key(provider, account_id)] = blob
        self._save(data)

    def delete(self, provider: str, account_id: str) -> bool:
        data = self._load()
        if self._key(provider, account_id) not in data:
            return False
        del data[self._key(provider, account_id)]
        self._save(data)
        return True

    def count(self) -> int:
        return len(self._load())
