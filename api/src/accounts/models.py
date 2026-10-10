"""Accounts and memberships. See docs/LLD-shared-accounts-and-iam.md.

An account owns resources, billing and quotas. A membership links an identity to an account and has no
role: what a member may do comes from the policies attached to it, so the creator is made an admin by
attaching `AdministratorAccess`.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

ADMINISTRATOR_ACCESS = "AdministratorAccess"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    PENDING_DELETION = "pending_deletion"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


def personal_account_id(user_id: str) -> str:
    """Derived from the person, so racing or retried sign-ins can only ever create one personal account."""
    return str(uuid5(NAMESPACE_URL, f"personal-account:{user_id}"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Account:
    name: str
    created_by: str
    account_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = AccountStatus.ACTIVE.value
    # Bumped on every permission change, so cached permissions for the old version are never used
    authz_version: int = 1
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return "Account#Metadata"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {"pk": self.pk, "sk": self.sk, **asdict(self)}

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Account":
        return cls(
            name=item["name"],
            created_by=item["created_by"],
            account_id=item["account_id"],
            status=item.get("status", AccountStatus.ACTIVE.value),
            authz_version=int(item.get("authz_version", 1)),
            created_at=item["created_at"],
            updated_at=item.get("updated_at", item["created_at"]),
        )


@dataclass
class Member:
    """A membership. The email and name are copies from the identity, kept for member lists."""

    account_id: str
    user_id: str
    email: str
    name: str
    status: str = MemberStatus.ACTIVE.value
    invited_by: Optional[str] = None
    joined_at: str = field(default_factory=_now)

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return f"Member#{self.user_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            # The reverse lookup: every account a person belongs to, in one query
            "gsi2_pk": f"Identity#{self.user_id}",
            "gsi2_sk": f"Membership#{self.account_id}",
            **asdict(self),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Member":
        return cls(
            account_id=item["account_id"],
            user_id=item["user_id"],
            email=item["email"],
            name=item["name"],
            status=item.get("status", MemberStatus.ACTIVE.value),
            invited_by=item.get("invited_by"),
            joined_at=item["joined_at"],
        )


def member_attachment_item(account_id: str, user_id: str, policy: str, attached_by: str) -> dict[str, Any]:
    """A policy attached to a member. The IAM module (KAN-77) owns attachments; accounts only write the first."""
    return {
        "pk": f"Account#{account_id}",
        "sk": f"Attachment#member#{user_id}#{policy}",
        "principal_type": "member",
        "principal_id": user_id,
        "policy": policy,
        "attached_by": attached_by,
        "attached_at": _now(),
    }


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class AccountResponse(BaseModel):
    account_id: str
    name: str
    status: str
    created_at: str


class MembershipResponse(BaseModel):
    account_id: str
    name: str
    # "admin" or "member" until custom policies arrive (KAN-77)
    access_summary: str
    membership_status: str
    joined_at: str
