"""Registry metadata and credential blob storage."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from lairen.errors import LairenError
from lairen.models import Account
from lairen.util import atomic_write_text

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+@-]{0,63}$")


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
                if account.alias is None:
                    account.alias = existing.alias
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

        alias_matches = [account for account in accounts if account.alias == ref]
        if alias_matches:
            return self._only(ref, alias_matches)
        id_matches = [account for account in accounts if account.id == ref]
        if id_matches:
            return self._only(ref, id_matches)
        label_matches = [account for account in accounts if account.label == ref]
        if label_matches:
            return self._only(ref, label_matches)
        raise LairenError(f"unknown account: {ref}")

    @staticmethod
    def _only(ref: str, matches: Sequence[Account]) -> Account:
        if len(matches) == 1:
            return matches[0]
        refs = ", ".join(account.ref for account in matches)
        raise LairenError(f"ambiguous account {ref!r}; use one of: {refs}")

    def validate_alias(
        self,
        alias: str,
        provider: str | None = None,
        account_id: str | None = None,
    ) -> str:
        """Return a normalized alias, rejecting invalid or conflicting names."""
        skip = (
            (provider, account_id)
            if provider is not None and account_id is not None
            else None
        )
        return self._validate_alias(self.load(), alias, skip)

    @staticmethod
    def _validate_alias(
        accounts: Sequence[Account],
        alias: str,
        skip: tuple[str, str] | None = None,
    ) -> str:
        value = alias.strip()
        if not ALIAS_PATTERN.fullmatch(value):
            raise LairenError(
                "alias must start with a letter or digit, contain only letters, "
                "digits, '.', '_', '+', '@', '-', and be at most 64 characters"
            )
        for account in accounts:
            if skip == (account.provider, account.id):
                continue
            if account.alias == value:
                raise LairenError(f"alias {value!r} is already used by {account.ref}")
            if account.id == value:
                raise LairenError(f"alias {value!r} conflicts with account id {account.ref}")
            if account.label == value:
                raise LairenError(f"alias {value!r} conflicts with label {account.ref}")
        return value

    def set_alias(self, provider: str, account_id: str, alias: str) -> Account:
        accounts = self.load()
        for account in accounts:
            if account.provider == provider and account.id == account_id:
                account.alias = self._validate_alias(
                    accounts, alias, (provider, account_id)
                )
                self.save(accounts)
                return account
        raise LairenError(f"unknown account: {provider}/{account_id}")

    def clear_alias(self, provider: str, account_id: str) -> Account:
        accounts = self.load()
        for account in accounts:
            if account.provider == provider and account.id == account_id:
                account.alias = None
                self.save(accounts)
                return account
        raise LairenError(f"unknown account: {provider}/{account_id}")

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
