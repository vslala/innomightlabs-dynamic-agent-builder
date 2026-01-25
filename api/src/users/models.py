from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING_DELETION = "pending_deletion"


@dataclass
class User:
    email: str
    name: str
    picture: Optional[str] = None
    refresh_token: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    status: str = UserStatus.ACTIVE.value
    deletion_requested_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    ttl: Optional[int] = None

    def __post_init__(self):
        now = datetime.utcnow().isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    @property
    def pk(self) -> str:
        return f"User#{self.email}"

    @property
    def sk(self) -> str:
        return "User#Metadata"

    def to_dynamo_item(self) -> dict:
        item = {
            "pk": self.pk,
            "sk": self.sk,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
            "refresh_token": self.refresh_token,
            "stripe_customer_id": self.stripe_customer_id,
            "status": self.status,
            "deletion_requested_at": self.deletion_requested_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
        }
        if self.ttl is not None:
            item["ttl"] = self.ttl
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "User":
        return cls(
            email=item["email"],
            name=item["name"],
            picture=item.get("picture"),
            refresh_token=item.get("refresh_token"),
            stripe_customer_id=item.get("stripe_customer_id"),
            status=item.get("status", UserStatus.ACTIVE.value),
            deletion_requested_at=item.get("deletion_requested_at"),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
            password_hash=item.get("password_hash"),
            password_salt=item.get("password_salt"),
            ttl=item.get("ttl"),
        )

    def to_dict(self) -> dict:
        return asdict(self)
