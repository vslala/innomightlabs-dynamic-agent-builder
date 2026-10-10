"""The escalation guard: you can only grant what you hold. See docs/LLD-shared-accounts-and-iam.md,
"Changing permissions safely". Pure, like the engine.

An Allow grants (action, resource) pairs. The caller must hold each pair through an Allow of their own
that is unconditional and at least as broad, with no Deny of theirs touching it. Deny statements grant
nothing and are never restricted. An Allow conditioned on ownership grants only what OwnerAccess
already gives everyone, so it passes.

Until resources carry an account owner (KAN-80) and shares exist (KAN-78), a specific `type/id` is
judged the same way, without the caller's ownership or shares: the guard can refuse a grant the caller
could justify, never allow one they couldn't.
"""

from typing import Optional, Sequence

from .actions import ACCOUNT, CATALOG
from .engine import NamedPolicy
from .policy import PolicyDocument


def ungrantable(caller_policies: Sequence[NamedPolicy], document: PolicyDocument) -> list[str]:
    """The grants in `document` the caller doesn't hold, as "action on resource"; empty when it may grant."""
    missing = []
    for statement in document.statements:
        if statement.effect != "Allow" or statement.condition is not None:
            continue
        for action in sorted(statement.expanded_actions):
            for pattern in statement.resources:
                granted = _scope(action, pattern)
                if granted is not None and not _held(action, granted, caller_policies):
                    missing.append(f"{action} on {pattern}")
    return missing


def _scope(action: str, pattern: str) -> Optional[str]:
    """What a resource pattern means for one action: `*` on an agent action is `agent/*`. None when the
    pattern can't name what the action acts on, so it grants nothing."""
    resource_type = CATALOG[action].resource_type
    if resource_type == ACCOUNT:
        return "*" if pattern == "*" else None
    if pattern == "*":
        return f"{resource_type}/*"
    return pattern if pattern.split("/", 1)[0] == resource_type else None


def _covers(held: str, wanted: str) -> bool:
    return held == wanted or (held.endswith("/*") and wanted.startswith(held[:-1]))


def _held(action: str, wanted: str, policies: Sequence[NamedPolicy]) -> bool:
    allowed = False
    for policy in policies:
        for statement in policy.document.statements:
            if action not in statement.expanded_actions:
                continue
            scopes = [scope for pattern in statement.resources if (scope := _scope(action, pattern))]
            if statement.effect == "Deny":
                # Any Deny that could touch the grant, conditioned or not, refuses it
                if any(_covers(scope, wanted) or _covers(wanted, scope) for scope in scopes):
                    return False
            elif statement.condition is None and any(_covers(scope, wanted) for scope in scopes):
                allowed = True
    return allowed
