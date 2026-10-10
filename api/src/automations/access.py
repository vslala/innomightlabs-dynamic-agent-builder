"""Reaching an automation: find it in the account, then check the action, as for agents
(`src/agents/access.py`). See docs/LLD-shared-accounts-and-iam.md, "Enforcement in routes".
"""

from typing import Annotated, Callable, Optional

from fastapi import Depends, HTTPException

from src.accounts.owner import Owner
from src.automations.models import Automation, AutomationAccess, AutomationStatus
from src.automations.repository import AutomationRepository
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.iam.shares import RESOLVERS
from src.identity import IdentityRepository


def require_automation(principal: Principal, automation_id: str, action: str,
                       repository: Optional[AutomationRepository] = None) -> Automation:
    """The live automation, if the caller may `action` it: 404 when they can't even see it, 403 when they
    can."""
    automation = (repository or AutomationRepository()).find_in_account(principal.account_id, automation_id)
    if automation is None or automation.status == AutomationStatus.DELETED:
        raise HTTPException(status_code=404, detail="Automation not found")
    principal.require(action, automation.resource_ref)
    return automation


def automation_with(action: str) -> Callable[..., Automation]:
    """A route dependency: the path's automation, once the caller may `action` it."""

    def dependency(automation_id: str, principal: Annotated[Principal, Depends(get_principal)]) -> Automation:
        return require_automation(principal, automation_id, action)

    return dependency


def access_to(principal: Principal, automation: Automation) -> Optional[AutomationAccess]:
    """How the caller reaches the automation, or None when they can't see it."""
    if automation.owner_id == principal.user_id:
        return "owner"
    if not principal.can("automations:Describe", automation.resource_ref).allowed:
        return None
    return "shared" if principal.can("automations:Get", automation.resource_ref).allowed else "admin"


def visible_automations(principal: Principal, repository: Optional[AutomationRepository] = None
                        ) -> list[tuple[Automation, AutomationAccess]]:
    """The account's automations the caller can see: their own, those shared with them, and (for admins)
    everyone else's as metadata."""
    visible = []
    for automation in (repository or AutomationRepository()).list_in_account(principal.account_id):
        access = access_to(principal, automation)
        if access:
            visible.append((automation, access))
    return visible


def owner_of_automation(automation: Automation) -> Owner:
    """The member an automation runs as, whoever edits or starts it: their agents, connectors and settings."""
    identity = IdentityRepository().get(automation.owner_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return Owner(account_id=automation.account_id, user_id=automation.owner_id, email=identity.email)


def _resolve(account_id: str, automation_id: str) -> Optional[ResourceRef]:
    automation = AutomationRepository().find_in_account(account_id, automation_id)
    return automation.resource_ref if automation and automation.status != AutomationStatus.DELETED else None


RESOLVERS["automation"] = _resolve
