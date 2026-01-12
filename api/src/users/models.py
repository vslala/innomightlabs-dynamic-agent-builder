from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class User:
    email: str
    name: str
    picture: Optional[str] = None
    refresh_token: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

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
        return {
            "pk": self.pk,
            "sk": self.sk,
            "email": self.email,
            "name": self.name,
            "picture": self.picture,
            "refresh_token": self.refresh_token,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "User":
        return cls(
            email=item["email"],
            name=item["name"],
            picture=item.get("picture"),
            refresh_token=item.get("refresh_token"),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )

    def to_dict(self) -> dict:
        return asdict(self)
