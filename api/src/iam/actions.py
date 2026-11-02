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

    @property
    def service(self) -> str:
        return self.name.split(":", 1)[0]

    @property
    def verb(self) -> str:
        return self.name.split(":", 1)[1]

    @property
    def names_a_resource(self) -> bool:
        """
        True when the action acts on one resource (`agent/{id}`), the only kind that has an owner. Create, List
        and account-wide actions name none, so the owner condition never allows them.
        """
        return self.resource_type != ACCOUNT and self.verb not in _COLLECTION_VERBS


@dataclass(frozen=True)
class ResourceRef:
    """What a request acts on. Account-wide actions and Create/List name no id."""

    type: str  # "agent", or ACCOUNT
    id: Optional[str] = None
    owner_id: Optional[str] = None  # a user_id; None for the account and for Create/List

    @property
    def name(self) -> str:
        return f"{self.type}/{self.id}" if self.id else "*"


@dataclass(frozen=True)
class Service:
    """A group of actions, shown together in the IAM portal (Agents, Knowledge bases, ...)."""

    name: str  # the prefix in action names: "agents"
    label: str
    summary: str
    resource_type: str
    metadata: tuple[str, ...] = ()
    contents: tuple[str, ...] = ()

    @property
    def actions(self) -> list[Action]:
        return [Action(f"{self.name}:{verb}", self.resource_type, False) for verb in self.metadata] + [
            Action(f"{self.name}:{verb}", self.resource_type, True) for verb in self.contents
        ]


_COLLECTION_VERBS = frozenset({"Create", "List"})
_OWNED = ("Create", "List", "Describe", "Delete", "Transfer", "Share")

SERVICES: tuple[Service, ...] = (
    Service("agents", "Agents", "Agents, their settings and chatting with them", "agent",
            metadata=_OWNED, contents=("Get", "Update", "Chat")),
    Service("knowledge", "Knowledge bases", "Knowledge bases, their documents and crawls", "knowledge-base",
            metadata=_OWNED, contents=("Get", "Update", "Crawl")),
    Service("automations", "Automations", "Automations and running them", "automation",
            metadata=_OWNED, contents=("Get", "Update", "Run")),
    Service("kits", "Kits", "Solution kits built with Ila, applying and rolling them back", "kit",
            metadata=_OWNED, contents=("Get", "Apply", "Rollback")),
    # Skills and keys belong to an agent, so their verbs are named apart from Create/List: the
    # "create your own" wildcards (`*:Create` on `*`) must not reach into someone else's agent.
    Service("skills", "Agent skills", "Installing and configuring an agent's skills", "agent",
            contents=("Install", "Configure", "Uninstall")),
    Service("apikeys", "API keys", "An agent's widget and API keys", "agent",
            metadata=("ListKeys",), contents=("CreateKey", "RevokeKey")),
    # Conversations belong to one member and are never shared in v1, so there is no Share
    Service("conversations", "Conversations", "Conversations with agents", "conversation",
            metadata=("List", "Describe", "Delete"), contents=("Read",)),
    # The account's credentials and settings: provider keys, MCP connections, A2A, dream, smart suggestions.
    # Admins manage them; every member's agents use them.
    Service("settings", "Settings and MCP connections",
            "Provider keys, MCP connections, A2A, dream and smart suggestion settings", ACCOUNT,
            metadata=("Manage",)),
    # Lead forms are account configuration and captures are account data. The verbs are named apart from
    # List/Describe so the member and view-only wildcards don't reach visitors' personal data.
    Service("leads", "Leads", "Lead forms, lead settings and the captured leads", ACCOUNT,
            metadata=("ListForms", "ManageForms", "ManageSettings", "ViewCaptures", "ManageCaptures")),
    Service("iam", "Members and permissions", "Inviting and removing members, groups and policies", ACCOUNT,
            metadata=("ListMembers", "ListGroups", "ListPolicies", "Invite",
                      "ManageMembers", "ManageGroups", "ManagePolicies", "AttachPolicies")),
    Service("billing", "Billing", "The account's plan and payment", ACCOUNT, metadata=("View", "Manage")),
    Service("audit", "Audit log", "Reading who changed what", ACCOUNT, metadata=("Read",)),
    Service("account", "Account", "Renaming or deleting the account", ACCOUNT, metadata=("Update", "Delete")),
)

CATALOG: dict[str, Action] = {action.name: action for service in SERVICES for action in service.actions}

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
