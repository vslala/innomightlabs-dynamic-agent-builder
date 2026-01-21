from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UsageRecord:
    user_email: str
    period_key: str
    messages_used: int = 0
    kb_pages_used: int = 0
    agents_active: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        now = datetime.utcnow().isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return f"Usage#{self.period_key}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "user_email": self.user_email,
            "period_key": self.period_key,
            "messages_used": self.messages_used,
            "kb_pages_used": self.kb_pages_used,
            "agents_active": self.agents_active,
            "entity_type": "Usage",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "UsageRecord":
        return cls(
            user_email=item["user_email"],
            period_key=item["period_key"],
            messages_used=item.get("messages_used", 0),
            kb_pages_used=item.get("kb_pages_used", 0),
            agents_active=item.get("agents_active", 0),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
