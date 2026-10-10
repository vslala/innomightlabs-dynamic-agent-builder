"""Deciding a request, the way IAM does within one account. Pure: no I/O, so it is tested with tables.

1. A matching explicit Deny in any of the caller's policies refuses the request, whatever else allows it.
2. Otherwise an Allow from one of those policies, or a share on the resource, permits it.
3. Otherwise it is refused (implicit deny).
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Optional, Sequence

from .actions import CATALOG, ResourceRef
from .policy import PolicyDocument


@dataclass(frozen=True)
class NamedPolicy:
    name: str  # a built-in name ("AdministratorAccess") or "custom:{policy_id}"
    document: PolicyDocument


@dataclass(frozen=True)
class Share:
    """A grant of fixed actions on one resource to a member or group (stored by KAN-78)."""

    actions: frozenset[str]
    grantee: str  # "member/{user_id}" or "group/{group_id}"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Literal["explicit_deny", "allow", "share", "implicit_deny"]
    policy: Optional[str] = None  # the policy whose statement decided, or the share's grantee
    sid: Optional[str] = None


def evaluate(
    principal_id: str,
    action: str,
    resource: ResourceRef,
    policies: Sequence[NamedPolicy],
    load_shares: Callable[[], Iterable[Share]] = lambda: (),
) -> Decision:
    """Shares are loaded only when no policy decided, so acting on your own resource never reads them."""
    known = CATALOG.get(action)
    if known is None or known.resource_type != resource.type:
        # A route asked about an action that doesn't exist or doesn't apply here: a bug, not a denial
        raise ValueError(f"{action} is not an action on {resource.type}")

    matches = [
        (policy, statement)
        for policy in policies
        for statement in policy.document.statements
        if statement.matches(action, resource, principal_id)
    ]
    for policy, statement in matches:
        if statement.effect == "Deny":
            return Decision(False, "explicit_deny", policy.name, statement.sid)
    if matches:
        policy, statement = matches[0]
        return Decision(True, "allow", policy.name, statement.sid)
    if resource.id:
        for share in load_shares():
            if action in share.actions:
                return Decision(True, "share", share.grantee)
    return Decision(False, "implicit_deny")
