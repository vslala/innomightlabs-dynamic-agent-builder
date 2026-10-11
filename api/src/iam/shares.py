"""Sharing one resource with a member or group of the same account: the v1 form of an IAM resource
policy. See docs/LLD-shared-accounts-and-iam.md, "Shares".

    Account#{aid} / Share#{type}#{rid}#{member|group}#{id}
        gsi2: Account#{aid}#Grantee#{member|group}#{id} / Share#{type}#{rid}   "shared with me"

Shares have their own sk prefix, so listing a type (`begins_with(sk, "Agent#")`) never returns them.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal, Optional

from boto3.dynamodb.conditions import Key

from ..config import settings
from ..db import get_dynamodb_resource
from .actions import CATALOG, SHAREABLE_TYPES, ResourceRef, describe_action_for, share_action_for
from .engine import Decision, Share, evaluate
from .models import AccountIam, PrincipalType, now
from .repository import IamRepository
from .service import IamError, IamService, find_group, find_member

Preset = Literal["viewer", "user", "editor"]

# What each preset grants, per resource type. Delete, Transfer and Share are never in a preset.
PRESETS: dict[str, dict[str, tuple[str, ...]]] = {
    "agent": {
        "viewer": ("agents:Describe", "agents:Get"),
        "user": ("agents:Describe", "agents:Get", "agents:Chat"),
        "editor": ("agents:Describe", "agents:Get", "agents:Chat", "agents:Update", "skills:Configure"),
    },
    "knowledge-base": {
        "viewer": ("knowledge:Describe", "knowledge:Get"),
        "user": ("knowledge:Describe", "knowledge:Get"),
        "editor": ("knowledge:Describe", "knowledge:Get", "knowledge:Update", "knowledge:Crawl"),
    },
    "automation": {
        "viewer": ("automations:Describe", "automations:Get"),
        "user": ("automations:Describe", "automations:Get", "automations:Run"),
        "editor": ("automations:Describe", "automations:Get", "automations:Run", "automations:Update"),
    },
    "kit": {
        "viewer": ("kits:Describe", "kits:Get"),
        "user": ("kits:Describe", "kits:Get", "kits:Apply"),
        "editor": ("kits:Describe", "kits:Get", "kits:Apply", "kits:Rollback"),
    },
}

# Account-level actions that name no resource can't be granted on one; moving ownership stays with
# the owner and admins
_NEVER_SHARED_VERBS = {"Create", "List", "Transfer"}


def shareable_actions(resource_type: str) -> list[str]:
    """What the advanced mode can pick from for one resource type."""
    return [name for name, action in CATALOG.items()
            if action.resource_type == resource_type and name.split(":", 1)[1] not in _NEVER_SHARED_VERBS]


# How to find a resource, and its owner, in an account: one resolver per shareable type. Resources
# move into accounts in KAN-80, which registers them; until then sharing finds nothing.
Resolver = Callable[[str, str], Optional[ResourceRef]]
RESOLVERS: dict[str, Resolver] = {}


@dataclass(frozen=True)
class ResourceShare:
    resource_type: str
    resource_id: str
    grantee_type: PrincipalType
    grantee_id: str
    actions: tuple[str, ...]
    preset: Optional[str]  # None when the actions were picked one by one
    granted_by: str
    granted_at: str = field(default_factory=now)

    @property
    def grantee(self) -> str:
        return f"{self.grantee_type}/{self.grantee_id}"

    def item(self, account_id: str) -> dict[str, Any]:
        return {
            "pk": f"Account#{account_id}",
            "sk": share_sk(self.resource_type, self.resource_id, self.grantee_type, self.grantee_id),
            "gsi2_pk": f"Account#{account_id}#Grantee#{self.grantee_type}#{self.grantee_id}",
            "gsi2_sk": f"Share#{self.resource_type}#{self.resource_id}",
            "resource_type": self.resource_type, "resource_id": self.resource_id,
            "grantee_type": self.grantee_type, "grantee_id": self.grantee_id,
            "actions": list(self.actions), "preset": self.preset,
            "granted_by": self.granted_by, "granted_at": self.granted_at,
        }

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "ResourceShare":
        return cls(resource_type=item["resource_type"], resource_id=item["resource_id"],
                   grantee_type=item["grantee_type"], grantee_id=item["grantee_id"],
                   actions=tuple(item["actions"]), preset=item.get("preset"),
                   granted_by=item["granted_by"], granted_at=item["granted_at"])

    def as_grant(self) -> Share:
        return Share(frozenset(self.actions), self.grantee)


def share_sk(resource_type: str, resource_id: str, grantee_type: str, grantee_id: str) -> str:
    return f"Share#{resource_type}#{resource_id}#{grantee_type}#{grantee_id}"


class ShareRepository:
    GSI2_NAME = "gsi2"

    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def for_principal(self, account_id: str, resource: ResourceRef, user_id: str,
                      group_ids: Iterable[str]) -> list[ResourceShare]:
        """The shares on one resource that reach this member: theirs and their groups'. Exact keys, one read."""
        if not resource.id:
            return []
        grantees = [("member", user_id), *(("group", group_id) for group_id in sorted(group_ids))]
        keys = [{"pk": f"Account#{account_id}", "sk": share_sk(resource.type, resource.id, kind, grantee)}
                for kind, grantee in grantees]
        found: list[ResourceShare] = []
        for start in range(0, len(keys), 100):
            request: dict[str, Any] = {self.table.name: {"Keys": keys[start:start + 100]}}
            while request:
                response = self.dynamodb.batch_get_item(RequestItems=request)
                found += [ResourceShare.from_item(item) for item in response["Responses"].get(self.table.name, [])]
                request = response.get("UnprocessedKeys") or {}
        return found

    def on_resource(self, account_id: str, resource_type: str, resource_id: str) -> list[ResourceShare]:
        return [ResourceShare.from_item(item) for item in self._query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}")
            & Key("sk").begins_with(f"Share#{resource_type}#{resource_id}#"),
        )]

    def shared_with(self, account_id: str, user_id: str, group_ids: Iterable[str]) -> list[ResourceShare]:
        """Everything shared with the member, directly or through a group: the "Shared with me" view."""
        found: list[ResourceShare] = []
        for kind, grantee in [("member", user_id), *(("group", group_id) for group_id in sorted(group_ids))]:
            found += [ResourceShare.from_item(item) for item in self._query(
                IndexName=self.GSI2_NAME,
                KeyConditionExpression=Key("gsi2_pk").eq(f"Account#{account_id}#Grantee#{kind}#{grantee}"),
            )]
        return found

    def _query(self, **query: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def decide(state: AccountIam, user_id: str, action: str, resource: ResourceRef,
           shares: Optional[ShareRepository] = None) -> Decision:
    """The engine's decision for a member, consulting the shares that reach them only if needed."""
    repository = shares or ShareRepository()
    return evaluate(
        user_id, action, resource, state.policies_for(user_id),
        lambda: [share.as_grant() for share in
                 repository.for_principal(state.account_id, resource, user_id, state.group_ids_of(user_id))],
    )


class ShareService:
    """Writes go through `IamRepository.commit`: each bumps `authz_version`, judged on the state it changes."""

    def __init__(self, iam: Optional[IamService] = None, shares: Optional[ShareRepository] = None) -> None:
        self.iam = iam or IamService()
        self.shares = shares or ShareRepository()

    def resolve(self, account_id: str, resource_type: str, resource_id: str) -> ResourceRef:
        resolver = RESOLVERS.get(resource_type)
        resource = resolver(account_id, resource_id) if resolver else None
        if resource is None:
            raise IamError(404, "NOT_FOUND", f"{resource_type} not found")
        return resource

    def who_has_access(self, account_id: str, caller: str, resource: ResourceRef) -> list[ResourceShare]:
        """Who has access, for the Share dialog. Seen by anyone who may share the resource."""
        self._may_share(self.iam.state(account_id, caller), caller, resource)
        return self.shares.on_resource(account_id, resource.type, str(resource.id))

    def share(self, account_id: str, caller: str, resource: ResourceRef, grantee_type: PrincipalType,
              grantee_id: str, preset: Optional[Preset] = None,
              actions: Optional[list[str]] = None) -> ResourceShare:
        """Grant a preset, or actions picked one by one; sharing again with a grantee replaces their access."""
        state = self.iam.state(account_id, caller)
        self._may_share(state, caller, resource)
        granted = self._actions(resource.type, preset, actions)
        # You can only share what you can do yourself
        missing = [action for action in granted if not decide(state, caller, action, resource, self.shares).allowed]
        if missing:
            raise IamError(403, "ESCALATION", "You can only share what you can do yourself", missing=missing)
        if grantee_type == "group":
            find_group(state, grantee_id)
        else:
            find_member(state, grantee_id)
        share = ResourceShare(resource_type=resource.type, resource_id=str(resource.id), grantee_type=grantee_type,
                              grantee_id=grantee_id, actions=granted, preset=preset if not actions else None,
                              granted_by=caller)
        self.iam.commit(state, put=[share.item(account_id)])
        return share

    def revoke(self, account_id: str, caller: str, resource: ResourceRef, grantee_type: PrincipalType,
               grantee_id: str) -> None:
        state = self.iam.state(account_id, caller)
        self._may_share(state, caller, resource)
        key = {"pk": f"Account#{account_id}", "sk": share_sk(resource.type, str(resource.id), grantee_type, grantee_id)}
        if not [share for share in self.shares.on_resource(account_id, resource.type, str(resource.id))
                if (share.grantee_type, share.grantee_id) == (grantee_type, grantee_id)]:
            return
        self.iam.commit(state, delete=[key])

    def forget_resource(self, account_id: str, resource_type: str, resource_id: str) -> None:
        """Every share on a resource being deleted; the resource's own delete route has already authorized it."""
        found = self.shares.on_resource(account_id, resource_type, resource_id)
        if not found:
            return
        state = IamRepository().load(account_id)
        if state is not None:
            self.iam.commit(state, delete=[share.item(account_id) for share in found])

    def _may_share(self, state: AccountIam, caller: str, resource: ResourceRef) -> None:
        if resource.type not in SHAREABLE_TYPES:
            raise IamError(400, "NOT_SHAREABLE", f"A {resource.type} can't be shared")
        decision = decide(state, caller, share_action_for(resource.type), resource, self.shares)
        if decision.allowed:
            return
        if not decide(state, caller, describe_action_for(resource.type), resource, self.shares).allowed:
            raise IamError(404, "NOT_FOUND", f"{resource.type} not found")
        raise IamError(403, "ACCESS_DENIED", f"You are not allowed {share_action_for(resource.type)}",
                       action=share_action_for(resource.type), reason=decision.reason)

    @staticmethod
    def _actions(resource_type: str, preset: Optional[str], actions: Optional[list[str]]) -> tuple[str, ...]:
        if actions:
            allowed = shareable_actions(resource_type)
            unknown = [action for action in actions if action not in allowed]
            if unknown:
                raise IamError(422, "INVALID_SHARE", f"These can't be shared on a {resource_type}",
                               errors=unknown, allowed=allowed)
            return tuple(dict.fromkeys(actions))
        if preset is None or preset not in PRESETS[resource_type]:
            raise IamError(422, "INVALID_SHARE", "Choose a preset (viewer, user, editor) or actions")
        return PRESETS[resource_type][preset]
