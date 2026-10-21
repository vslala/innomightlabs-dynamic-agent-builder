"""Social accounts an InnomightLabs account has connected, to post to. See docs/LLD-social-cross-posting.md."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.crypto import decrypt
from src.utils.dynamodb import convert_decimals

#: How long before a token runs out the dashboard starts saying so.
EXPIRY_WARNING = timedelta(days=14)


class SocialAccountStatus(str, Enum):
    ACTIVE = "active"
    #: The network refused the token, or it ran out: the person has to connect again.
    NEEDS_RECONNECT = "needs_reconnect"


def external_key(account_id: str, network: str, external_id: str) -> dict[str, str]:
    """Guards one network identity to one connection per account, so connecting it again updates it."""
    return {"pk": f"Account#{account_id}", "sk": f"SocialAccountExternal#{network}#{external_id}"}


class SocialAccount(BaseModel):
    """One postable identity on a network (a LinkedIn member, a Facebook Page, a Bluesky handle). It belongs to the
    InnomightLabs account, like its other connections: admins connect it, every member's agents may use it."""

    social_account_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    network: str
    #: The network's id for this identity; unique per account and network
    external_id: str
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    status: SocialAccountStatus = SocialAccountStatus.ACTIVE
    #: Fernet-encrypted JSON; its shape belongs to the network's strategy
    encrypted_credentials: str
    scopes: str = ""
    token_expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    #: The user_id of whoever connected it, for audit
    connected_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return f"SocialAccount#{self.social_account_id}"

    def credentials(self) -> dict[str, Any]:
        """What the network's strategy stored for this account (tokens and ids), decrypted. Never log or return it."""
        return dict(json.loads(decrypt(self.encrypted_credentials)))

    def effective_status(self, now: datetime | None = None) -> SocialAccountStatus:
        """A token that has run out needs reconnecting, whatever was last stored."""
        now = now or datetime.now(timezone.utc)
        if self.token_expires_at and self.token_expires_at <= now:
            return SocialAccountStatus.NEEDS_RECONNECT
        return self.status

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "SocialAccount",
            "social_account_id": self.social_account_id,
            "account_id": self.account_id,
            "network": self.network,
            "external_id": self.external_id,
            "handle": self.handle,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "status": self.status.value,
            "encrypted_credentials": self.encrypted_credentials,
            "scopes": self.scopes,
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "last_error": self.last_error,
            "connected_by": self.connected_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "SocialAccount":
        item = convert_decimals(item)
        return cls(
            social_account_id=item["social_account_id"],
            account_id=item["account_id"],
            network=item["network"],
            external_id=item["external_id"],
            handle=item["handle"],
            display_name=item["display_name"],
            avatar_url=item.get("avatar_url"),
            status=SocialAccountStatus(item.get("status", SocialAccountStatus.ACTIVE.value)),
            encrypted_credentials=item["encrypted_credentials"],
            scopes=item.get("scopes", ""),
            token_expires_at=datetime.fromisoformat(item["token_expires_at"]) if item.get("token_expires_at") else None,
            last_error=item.get("last_error"),
            connected_by=item.get("connected_by", ""),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self, now: datetime | None = None) -> "SocialAccountResponse":
        return SocialAccountResponse(
            social_account_id=self.social_account_id,
            network=self.network,
            handle=self.handle,
            display_name=self.display_name,
            avatar_url=self.avatar_url,
            status=self.effective_status(now),
            token_expires_at=self.token_expires_at,
            last_error=self.last_error,
            created_at=self.created_at,
        )


class SocialAccountResponse(BaseModel):
    """What the dashboard shows: never the credentials."""

    social_account_id: str
    network: str
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    status: SocialAccountStatus
    token_expires_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime


class SocialNetworkResponse(BaseModel):
    """A network the account can connect an account on."""

    key: str
    display_name: str
    #: A brand mark key the dashboard knows (`spa/src/assets/connectors/<icon>.svg`)
    icon: str


class SocialConnectRequest(BaseModel):
    return_to: str


class SocialConnectResponse(BaseModel):
    authorize_url: str
