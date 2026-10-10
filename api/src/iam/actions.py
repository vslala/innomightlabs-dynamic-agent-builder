"""The action catalog: every action a policy can name. See docs/LLD-shared-accounts-and-iam.md.

Policies are validated against it, routes refer to it and the IAM portal draws its choices from it.
Adding a service is a new `_service(...)` line; policies using `service:*` pick its actions up.
"""

import fnmatch
from dataclasses import dataclass
from typing import Optional

# Account-wide actions (iam, billing, audit, account) act on the account itself, named `*` in policies
ACCOUNT = "account"


@dataclass(frozen=True)
class Action:
    name: str  # "agents:Chat"
    resource_type: str  # "agent"
    # True when the action reads or changes what is inside a resource (a prompt, documents, messages).
    # Admins hold only metadata actions on other members' resources.
    touches_contents: bool


@dataclass(frozen=True)
class ResourceRef:
    """What a request acts on. Account-wide actions and Create/List name no id."""

    type: str  # "agent", or ACCOUNT
    id: Optional[str] = None
    owner_id: Optional[str] = None  # a user_id; None for the account and for Create/List

    @property
    def name(self) -> str:
        return f"{self.type}/{self.id}" if self.id else "*"


def _service(service: str, resource_type: str, metadata: list[str], contents: list[str]) -> list[Action]:
    return [Action(f"{service}:{verb}", resource_type, False) for verb in metadata] + [
        Action(f"{service}:{verb}", resource_type, True) for verb in contents
    ]


_OWNED = ["Create", "List", "Describe", "Delete", "Transfer", "Share"]

CATALOG: dict[str, Action] = {
    action.name: action
    for action in [
        *_service("agents", "agent", metadata=_OWNED, contents=["Get", "Update", "Chat"]),
        *_service("knowledge", "knowledge-base", metadata=_OWNED, contents=["Get", "Update", "Crawl"]),
        *_service("automations", "automation", metadata=_OWNED, contents=["Get", "Update", "Run"]),
        *_service("kits", "kit", metadata=_OWNED, contents=["Get", "Apply", "Rollback"]),
        # Skills and keys belong to an agent, so their verbs are named apart from Create/List: the
        # "create your own" wildcards (`*:Create` on `*`) must not reach into someone else's agent.
        *_service("skills", "agent", metadata=[], contents=["Install", "Configure", "Uninstall"]),
        *_service("apikeys", "agent", metadata=["ListKeys"], contents=["CreateKey", "RevokeKey"]),
        # Conversations belong to one member and are never shared in v1, so there is no Share
        *_service("conversations", "conversation", metadata=["List", "Describe", "Delete"], contents=["Read"]),
        *_service("iam", ACCOUNT, metadata=[
            "ListMembers", "ListGroups", "ListPolicies", "Invite",
            "ManageMembers", "ManageGroups", "ManagePolicies", "AttachPolicies",
        ], contents=[]),
        *_service("billing", ACCOUNT, metadata=["View", "Manage"], contents=[]),
        *_service("audit", ACCOUNT, metadata=["Read"], contents=[]),
        *_service("account", ACCOUNT, metadata=["Update", "Delete"], contents=[]),
        # The account's credentials and settings: provider keys, MCP connections, A2A, dream, smart suggestions.
        # Admins manage them; every member's agents use them.
        *_service("settings", ACCOUNT, metadata=["Manage"], contents=[]),
    ]
}

# The types a policy's Resource can name (`agent/…`); account-wide actions take `*`
RESOURCE_TYPES: frozenset[str] = frozenset(action.resource_type for action in CATALOG.values()) - {ACCOUNT}

_DESCRIBE: dict[str, str] = {
    action.resource_type: action.name for action in CATALOG.values() if action.name.endswith(":Describe")
}
_SHARE: dict[str, str] = {
    action.resource_type: action.name for action in CATALOG.values() if action.name.endswith(":Share")
}
# Agents, knowledge bases, automations and kits; conversations stay private
SHAREABLE_TYPES: frozenset[str] = frozenset(_SHARE)


def expand(pattern: str) -> frozenset[str]:
    """Concrete action names matched by a pattern such as 'agents:*' or '*:List'."""
    return frozenset(name for name in CATALOG if fnmatch.fnmatchcase(name, pattern))


def describe_action_for(resource_type: str) -> str:
    """The action that lets a caller know a resource exists (`agents:Describe` for an agent)."""
    return _DESCRIBE[resource_type]


def share_action_for(resource_type: str) -> str:
    """The action that lets a caller share a resource (`agents:Share` for an agent)."""
    return _SHARE[resource_type]
