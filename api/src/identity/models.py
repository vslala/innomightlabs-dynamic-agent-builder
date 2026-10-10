"""A person who signs in. See docs/LLD-shared-accounts-and-iam.md.

The `user_id` never changes; the email is how the person signs in and is contacted, and can change.
Nothing is authorized by email: tokens carry the `user_id`.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class IdentityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING_DELETION = "pending_deletion"


def normalize_email(email: str) -> str:
    """The form the email index is keyed by. Gmail dots and +tags are kept: they are different addresses."""
    return email.strip().lower()


@dataclass
class Identity:
    email: str
    name: str
    user_id: str = field(default_factory=lambda: str(uuid4()))
    email_verified: bool = False
    picture: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    status: str = IdentityStatus.ACTIVE.value
    deletion_requested_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    ttl: Optional[int] = None

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    @property
    def pk(self) -> str:
        return f"Identity#{self.user_id}"

    @property
    def sk(self) -> str:
        return "Identity#Metadata"

    @property
    def is_active(self) -> bool:
        return self.status == IdentityStatus.ACTIVE.value

    def to_dynamo_item(self) -> dict[str, Any]:
        item = {"pk": self.pk, "sk": self.sk, **asdict(self)}
        if self.ttl is None:
            del item["ttl"]
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Identity":
        return cls(
            email=item["email"],
            name=item["name"],
            user_id=item["user_id"],
            email_verified=bool(item.get("email_verified", False)),
            picture=item.get("picture"),
            stripe_customer_id=item.get("stripe_customer_id"),
            status=item.get("status", IdentityStatus.ACTIVE.value),
            deletion_requested_at=item.get("deletion_requested_at"),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
            password_hash=item.get("password_hash"),
            password_salt=item.get("password_salt"),
            ttl=int(item["ttl"]) if item.get("ttl") is not None else None,
        )


def email_index_key(email: str) -> dict[str, str]:
    """One item per email, holding the identity it belongs to; its conditional put keeps emails unique."""
    return {"pk": f"Email#{normalize_email(email)}", "sk": "Email#Identity"}
