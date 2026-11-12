"""Account, stored-auth, and holder metadata objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lairen.util import utc_now


@dataclass
class Auth:
    """Metadata about the credential copy lairen keeps in its store."""

    stored: bool = False
    captured_at: str | None = None
    source_home: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stored": self.stored,
            "captured_at": self.captured_at,
            "source_home": self.source_home,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Auth:
        return cls(
            stored=bool(data.get("stored")),
            captured_at=data.get("captured_at"),
            source_home=data.get("source_home"),
        )


@dataclass
class Holder:
    """One live provider home attached to an account."""

    home: str
    recorded_at: str = field(default_factory=utc_now)
    verified_at: str | None = None
    stale_since: str | None = None
    stale_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home,
            "recorded_at": self.recorded_at,
            "verified_at": self.verified_at,
            "stale": (
                {
                    "since": self.stale_since,
                    "reason": self.stale_reason,
                }
                if self.stale_since
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Holder:
        raw_stale = data.get("stale")
        stale: dict[str, Any] = raw_stale if isinstance(raw_stale, dict) else {}
        return cls(
            home=str(data.get("home") or ""),
            recorded_at=str(data.get("recorded_at") or utc_now()),
            verified_at=data.get("verified_at"),
            stale_since=stale.get("since") or data.get("stale_since"),
            stale_reason=stale.get("reason") or data.get("stale_reason"),
        )


@dataclass
class Account:
    """One credential identity accepted by a provider CLI."""

    provider: str
    id: str
    label: str
    alias: str | None = None
    created_at: str = field(default_factory=utc_now)
    auth: Auth | None = None
    holder: Holder | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.provider}/{self.id}"

    @property
    def source_home(self) -> str | None:
        return self.auth.source_home if self.auth is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "id": self.id,
            "label": self.label,
            "alias": self.alias,
            "created_at": self.created_at,
            "auth": self.auth.to_dict() if self.auth is not None else None,
            "holder": self.holder.to_dict() if self.holder is not None else None,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        auth_data = data.get("auth")
        auth = Auth.from_dict(auth_data) if isinstance(auth_data, dict) else None
        if auth is None and data.get("source_home"):
            auth = Auth(stored=False, source_home=str(data["source_home"]))
        holder_data = data.get("holder")
        holder = Holder.from_dict(holder_data) if isinstance(holder_data, dict) else None
        raw_extra = data.get("extra")
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}
        return cls(
            provider=data["provider"],
            id=data["id"],
            label=data.get("label") or data["id"],
            alias=data.get("alias"),
            created_at=data.get("created_at") or utc_now(),
            auth=auth,
            holder=holder,
            extra=extra,
        )
