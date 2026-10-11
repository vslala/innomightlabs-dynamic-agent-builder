"""What an account stores to decide who may do what: groups, custom policies and their versions, and
attachments. All of it lives in the account's partition. See docs/LLD-shared-accounts-and-iam.md.

    Account#{aid} / Group#{gid}                                  a group
    Account#{aid} / GroupMember#{gid}#{uid}                      membership, read from the group
    Account#{aid} / Member#{uid}#Group#{gid}                     the same, read from the member
    Account#{aid} / Policy#{pid}                                 a custom policy
    Account#{aid} / Policy#{pid}#v{n}                            one of its versions (at most 5)
    Account#{aid} / Attachment#{member|group}#{id}#{policy}      policy: a built-in name or custom:{pid}
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from .builtins import ADMINISTRATOR_ACCESS, BUILTINS, OWNER_ACCESS
from .engine import NamedPolicy
from .policy import PolicyDocument

PrincipalType = Literal["member", "group"]

CUSTOM_PREFIX = "custom:"
MAX_POLICY_VERSIONS = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class Group:
    name: str
    created_by: str
    description: str = ""
    group_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)

    def item(self, account_id: str) -> dict[str, Any]:
        return {"pk": f"Account#{account_id}", "sk": f"Group#{self.group_id}", "group_id": self.group_id,
                "name": self.name, "description": self.description,
                "created_by": self.created_by, "created_at": self.created_at}

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "Group":
        return cls(name=item["name"], created_by=item["created_by"], description=item.get("description", ""),
                   group_id=item["group_id"], created_at=item["created_at"])


def group_membership_items(account_id: str, group_id: str, user_id: str) -> list[dict[str, Any]]:
    """Both halves: the group's member list and the member's group list."""
    pk = f"Account#{account_id}"
    return [
        {"pk": pk, "sk": f"GroupMember#{group_id}#{user_id}", "group_id": group_id, "user_id": user_id},
        {"pk": pk, "sk": f"Member#{user_id}#Group#{group_id}", "group_id": group_id, "user_id": user_id},
    ]


@dataclass(frozen=True)
class PolicyVersion:
    version: int
    document: PolicyDocument
    created_by: str
    created_at: str = field(default_factory=now)

    def item(self, account_id: str, policy_id: str) -> dict[str, Any]:
        # Stored as JSON text, so the document reads back exactly as written
        return {"pk": f"Account#{account_id}", "sk": f"Policy#{policy_id}#v{self.version}",
                "policy_id": policy_id, "version": self.version, "document": json.dumps(self.document.to_json()),
                "created_by": self.created_by, "created_at": self.created_at}

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "PolicyVersion":
        return cls(version=int(item["version"]), document=PolicyDocument.model_validate(json.loads(item["document"])),
                   created_by=item["created_by"], created_at=item["created_at"])


@dataclass(frozen=True)
class CustomPolicy:
    name: str
    created_by: str
    default_version: int
    latest_version: int
    versions: dict[int, PolicyVersion]
    description: str = ""
    policy_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now)

    @property
    def ref(self) -> str:
        return f"{CUSTOM_PREFIX}{self.policy_id}"

    @property
    def document(self) -> PolicyDocument:
        """What the policy grants: its default version."""
        return self.versions[self.default_version].document

    def item(self, account_id: str) -> dict[str, Any]:
        return {"pk": f"Account#{account_id}", "sk": f"Policy#{self.policy_id}", "policy_id": self.policy_id,
                "name": self.name, "description": self.description, "default_version": self.default_version,
                "latest_version": self.latest_version, "created_by": self.created_by, "created_at": self.created_at}

    @classmethod
    def from_item(cls, item: dict[str, Any], versions: dict[int, PolicyVersion]) -> "CustomPolicy":
        return cls(name=item["name"], created_by=item["created_by"], default_version=int(item["default_version"]),
                   latest_version=int(item["latest_version"]), versions=versions,
                   description=item.get("description", ""), policy_id=item["policy_id"],
                   created_at=item["created_at"])


@dataclass(frozen=True)
class Attachment:
    principal_type: PrincipalType
    principal_id: str
    policy: str  # a built-in name or custom:{policy_id}
    attached_by: str
    attached_at: str = field(default_factory=now)

    @property
    def sk(self) -> str:
        return f"Attachment#{self.principal_type}#{self.principal_id}#{self.policy}"

    def item(self, account_id: str) -> dict[str, Any]:
        return {"pk": f"Account#{account_id}", "sk": self.sk, "principal_type": self.principal_type,
                "principal_id": self.principal_id, "policy": self.policy,
                "attached_by": self.attached_by, "attached_at": self.attached_at}

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "Attachment":
        return cls(principal_type=item["principal_type"], principal_id=item["principal_id"], policy=item["policy"],
                   attached_by=item.get("attached_by", ""), attached_at=item.get("attached_at", ""))


@dataclass(frozen=True)
class EffectivePolicy:
    policy: NamedPolicy
    source: str  # "implicit", "account owner", "direct" or "group:{group_id}"


@dataclass(frozen=True)
class AccountIam:
    """Everything that decides permissions in one account, read at one `authz_version`."""

    account_id: str
    owner_id: str
    authz_version: int
    members: dict[str, str]  # user_id -> membership status
    groups: dict[str, Group]
    group_members: frozenset[tuple[str, str]]  # (group_id, user_id)
    attachments: dict[str, Attachment]  # by sk
    policies: dict[str, CustomPolicy]  # by policy_id

    def group_ids_of(self, user_id: str) -> frozenset[str]:
        return frozenset(group_id for group_id, member in self.group_members if member == user_id)

    def members_of(self, group_id: str) -> list[str]:
        return sorted(member for group, member in self.group_members if group == group_id)

    def attachments_of(self, principal_type: PrincipalType, principal_id: str) -> list[Attachment]:
        return [attachment for attachment in self.attachments.values()
                if (attachment.principal_type, attachment.principal_id) == (principal_type, principal_id)]

    def resolve(self, policy: str) -> Optional[NamedPolicy]:
        if policy.startswith(CUSTOM_PREFIX):
            custom = self.policies.get(policy[len(CUSTOM_PREFIX):])
            return NamedPolicy(custom.ref, custom.document) if custom else None
        return BUILTINS.get(policy)

    def effective_policies(self, user_id: str) -> list[EffectivePolicy]:
        """
        Where each of the member's policies comes from. OwnerAccess applies to everyone.

        The account's owner is its admin whatever is attached, like AWS's root user: they hold
        AdministratorAccess by owning the account, and their groups can add to it but never take
        anything away, so a Deny never applies to them.
        """
        is_owner = user_id == self.owner_id
        found = [EffectivePolicy(OWNER_ACCESS, "implicit")]
        if is_owner:
            found.append(EffectivePolicy(ADMINISTRATOR_ACCESS, "account owner"))
        sources: list[tuple[PrincipalType, str, str]] = [("member", user_id, "direct")] + [
            ("group", group_id, f"group:{group_id}") for group_id in sorted(self.group_ids_of(user_id))
        ]
        for principal_type, principal_id, source in sources:
            for attachment in self.attachments_of(principal_type, principal_id):
                named = self.resolve(attachment.policy)
                if named and is_owner:
                    named = _allows_only(named)
                if named:
                    found.append(EffectivePolicy(named, source))
        return found

    def policies_for(self, user_id: str) -> tuple[NamedPolicy, ...]:
        unique: dict[str, NamedPolicy] = {}
        for effective in self.effective_policies(user_id):
            unique.setdefault(effective.policy.name, effective.policy)
        return tuple(unique.values())


def _allows_only(policy: NamedPolicy) -> Optional[NamedPolicy]:
    allows = [statement for statement in policy.document.statements if statement.effect == "Allow"]
    if not allows:
        return None
    return NamedPolicy(policy.name, PolicyDocument.model_validate({"Version": policy.document.version, "Statement": allows}))
