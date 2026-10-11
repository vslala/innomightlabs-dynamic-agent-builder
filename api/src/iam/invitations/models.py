from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal

InviteStatus = Literal["pending", "accepted", "revoked", "expired"]
DeliveryStatus = Literal["pending", "sent", "failed"]


def token_digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Invite:
    account_id: str
    invite_id: str
    email: str
    invited_by: str
    expires_at: str
    ttl: int
    token_hash: str = field(repr=False)
    created_at: str
    status: InviteStatus = "pending"
    delivery_status: DeliveryStatus = "pending"
    accepted_by: str | None = None

    @property
    def key(self) -> dict[str, str]:
        return {"pk": f"Account#{self.account_id}", "sk": f"Invite#{self.invite_id}"}

    def item(self) -> dict[str, Any]:
        token_key = f"InviteToken#{self.token_hash}"
        return {**self.key, **asdict(self), "gsi2_pk": token_key, "gsi2_sk": token_key}

    def effective_status(self, timestamp: float) -> InviteStatus:
        if self.status == "pending" and datetime.fromisoformat(self.expires_at).timestamp() <= timestamp:
            return "expired"
        return self.status

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "Invite":
        return cls(**{name: item[name] for name in cls.__dataclass_fields__ if name in item})


def iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
