"""Account metadata objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lairen.util import utc_now


@dataclass
class Account:
    provider: str
    id: str
    label: str
    source_home: str
    created_at: str = field(default_factory=utc_now)
    last_deployed_at: str | None = None
    last_deployed_home: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.provider}/{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "id": self.id,
            "label": self.label,
            "source_home": self.source_home,
            "created_at": self.created_at,
            "last_deployed_at": self.last_deployed_at,
            "last_deployed_home": self.last_deployed_home,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        return cls(
            provider=data["provider"],
            id=data["id"],
            label=data.get("label") or data["id"],
            source_home=data.get("source_home", ""),
            created_at=data.get("created_at") or utc_now(),
            last_deployed_at=data.get("last_deployed_at"),
            last_deployed_home=data.get("last_deployed_home"),
            extra=data.get("extra") or {},
        )
