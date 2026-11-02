"""What a member may do, service by service: their policies read against the action catalog, the way the AWS
console summarises a policy. Pure, like the engine. It describes; `evaluate` still decides every request, and
shares (per-resource grants) are not part of it.

For each action it reports how far an Allow reaches and how far a Deny reaches:

- `all`: every resource of the type, or the account for account-wide actions;
- `some`: only the resources a statement names (`agent/8c1e…`);
- `own`: only resources they own (the `iml:ResourceOwner` condition), which can only apply to an action that
  names a resource, never to Create, List or an account-wide action.
"""

from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence

from .actions import ACCOUNT, SERVICES, Action, Service
from .engine import NamedPolicy

Scope = Literal["all", "some", "own"]
Level = Literal["all", "some", "own", "denied", "none"]
ServiceLevel = Literal["full", "limited", "none"]


@dataclass(frozen=True)
class Reach:
    """How far the statements of one effect reach for one action."""

    scope: Optional[Scope] = None
    resources: tuple[str, ...] = ()  # with `some`: the resources named
    policies: tuple[str, ...] = ()  # the policies those statements come from, by display name


@dataclass(frozen=True)
class ActionAccess:
    action: Action
    allow: Reach
    deny: Reach

    @property
    def level(self) -> Level:
        """What the member ends up with: an unconditional Deny on everything wins over any Allow."""
        if self.deny.scope == "all":
            return "denied"
        return self.allow.scope or "none"


@dataclass(frozen=True)
class ServiceAccess:
    service: Service
    actions: tuple[ActionAccess, ...]

    @property
    def level(self) -> ServiceLevel:
        levels = {access.level for access in self.actions}
        if levels == {"all"} and not any(access.deny.scope for access in self.actions):
            return "full"
        if levels <= {"none", "denied"}:
            return "none"
        return "limited"


def summarize(policies: Sequence[NamedPolicy]) -> list[ServiceAccess]:
    """Every service in the catalog, in catalog order, with each action's reach under these policies."""
    return [
        ServiceAccess(service, tuple(
            ActionAccess(action, _reach(policies, action, "Allow"), _reach(policies, action, "Deny"))
            for action in service.actions
        ))
        for service in SERVICES
    ]


def _reach(policies: Sequence[NamedPolicy], action: Action, effect: Literal["Allow", "Deny"]) -> Reach:
    everywhere: list[str] = []
    named: dict[str, list[str]] = {}  # resource -> policies
    owned: list[str] = []
    for policy in policies:
        for statement in policy.document.statements:
            if statement.effect != effect or action.name not in statement.expanded_actions:
                continue
            for pattern in statement.resources:
                if not _applies(pattern, action):
                    continue
                if statement.condition is not None:
                    # The owner condition: only a resource with an owner can meet it
                    if action.names_a_resource:
                        owned.append(policy.display_name)
                elif _covers_every(pattern, action):
                    everywhere.append(policy.display_name)
                else:
                    named.setdefault(pattern, []).append(policy.display_name)
    if everywhere:
        return Reach("all", policies=_unique(everywhere))
    if named:
        return Reach("some", tuple(sorted(named)), _unique(name for names in named.values() for name in names))
    if owned:
        return Reach("own", policies=_unique(owned))
    return Reach()


def _covers_every(pattern: str, action: Action) -> bool:
    return pattern == "*" or (action.resource_type != ACCOUNT and pattern == f"{action.resource_type}/*")


def _applies(pattern: str, action: Action) -> bool:
    """Whether a Resource pattern can match this action at all (as `_resource_matches` in policy.py decides)."""
    if _covers_every(pattern, action):
        return True
    # `agent/{id}` names one resource, so it only reaches actions that act on one, of that type
    return action.names_a_resource and pattern.split("/", 1)[0] == action.resource_type


def _unique(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))
