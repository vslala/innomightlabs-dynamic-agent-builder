"""Reaching a kit: find it in the account, then check the action, as for agents (`src/agents/access.py`).
See docs/LLD-shared-accounts-and-iam.md, "Enforcement in routes".
"""

from typing import Annotated, Callable, Literal, Optional

from fastapi import Depends, HTTPException

from src.blueprints.kits import Kit, KitRepository
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.iam.shares import RESOLVERS

KitAccess = Literal["owner", "shared", "admin"]


def require_kit(principal: Principal, kit_id: str, action: str) -> Kit:
    """The kit, if the caller may `action` it: 404 when they can't even see it, 403 when they can."""
    kit = KitRepository().find(principal.account_id, kit_id)
    if kit is None:
        raise HTTPException(status_code=404, detail="There's no such kit.")
    principal.require(action, kit.resource_ref)
    return kit


def kit_with(action: str) -> Callable[..., Kit]:
    """A route dependency: the path's kit, once the caller may `action` it."""

    def dependency(kit_id: str, principal: Annotated[Principal, Depends(get_principal)]) -> Kit:
        return require_kit(principal, kit_id, action)

    return dependency


def access_to(principal: Principal, kit: Kit) -> Optional[KitAccess]:
    """How the caller reaches the kit, or None when they can't see it."""
    if kit.owner_id == principal.user_id:
        return "owner"
    if not principal.can("kits:Describe", kit.resource_ref).allowed:
        return None
    return "shared" if principal.can("kits:Get", kit.resource_ref).allowed else "admin"


def visible_kits(principal: Principal) -> list[tuple[Kit, KitAccess]]:
    """The account's kits the caller can see: their own, those shared with them, and (for admins) everyone else's
    as metadata."""
    visible = []
    for kit in KitRepository().list_in_account(principal.account_id):
        access = access_to(principal, kit)
        if access:
            visible.append((kit, access))
    return visible


def _resolve(account_id: str, kit_id: str) -> Optional[ResourceRef]:
    kit = KitRepository().find(account_id, kit_id)
    return kit.resource_ref if kit else None


RESOLVERS["kit"] = _resolve
