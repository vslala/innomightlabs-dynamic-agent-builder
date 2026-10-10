"""Reaching a knowledge base: find it in the account, then check the action, as for agents
(`src/agents/access.py`). See docs/LLD-shared-accounts-and-iam.md, "Enforcement in routes".
"""

from typing import Annotated, Callable, Optional

from fastapi import Depends, HTTPException

from src.agents.models import Agent
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_principal
from src.iam.principal import Principal, load_principal
from src.iam.service import IamError
from src.iam.shares import RESOLVERS
from src.identity import IdentityRepository
from src.knowledge.models import KnowledgeBase, KnowledgeBaseAccess, KnowledgeBaseStatus
from src.knowledge.repository import KnowledgeBaseRepository


def require_kb(principal: Principal, kb_id: str, action: str,
               repository: Optional[KnowledgeBaseRepository] = None) -> KnowledgeBase:
    """The live knowledge base, if the caller may `action` it: 404 when they can't even see it, 403 when
    they can."""
    kb = (repository or KnowledgeBaseRepository()).find_in_account(principal.account_id, kb_id)
    if kb is None or kb.status == KnowledgeBaseStatus.DELETED:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    principal.require(action, kb.resource_ref)
    return kb


def kb_with(action: str) -> Callable[..., KnowledgeBase]:
    """A route dependency: the path's knowledge base, once the caller may `action` it."""

    def dependency(kb_id: str, principal: Annotated[Principal, Depends(get_principal)]) -> KnowledgeBase:
        return require_kb(principal, kb_id, action)

    return dependency


def access_to(principal: Principal, kb: KnowledgeBase) -> Optional[KnowledgeBaseAccess]:
    """How the caller reaches the knowledge base, or None when they can't see it."""
    if kb.owner_id == principal.user_id:
        return "owner"
    if not principal.can("knowledge:Describe", kb.resource_ref).allowed:
        return None
    return "shared" if principal.can("knowledge:Get", kb.resource_ref).allowed else "admin"


def visible_kbs(principal: Principal,
                repository: Optional[KnowledgeBaseRepository] = None) -> list[tuple[KnowledgeBase, KnowledgeBaseAccess]]:
    """The account's knowledge bases the caller can see: their own, those shared with them, and (for
    admins) everyone else's as metadata."""
    visible = []
    for kb in (repository or KnowledgeBaseRepository()).list_in_account(principal.account_id):
        access = access_to(principal, kb)
        if access:
            visible.append((kb, access))
    return visible


def readable_by_agent(agent: Agent, kb_ids: list[str],
                      repository: Optional[KnowledgeBaseRepository] = None) -> list[KnowledgeBase]:
    """The linked knowledge bases an agent may search: live, in its account, and readable by its owner,
    the member it runs as. A link outlives a share; revoking the share is what stops the reads."""
    repository = repository or KnowledgeBaseRepository()
    kbs = [kb for kb in (repository.find_in_account(agent.account_id, kb_id) for kb_id in kb_ids)
           if kb and kb.status != KnowledgeBaseStatus.DELETED]
    if all(kb.owner_id == agent.owner_id for kb in kbs):
        return kbs
    try:
        owner = load_principal(agent.owner_id, agent.account_id)
    except IamError:  # the owner has left the account: they read nothing in it
        return []
    return [kb for kb in kbs if kb.owner_id == agent.owner_id or owner.can("knowledge:Get", kb.resource_ref).allowed]


def owned_kb(kb_id: str, owner_email: str,
             repository: Optional[KnowledgeBaseRepository] = None) -> Optional[KnowledgeBase]:
    """The knowledge base, if the person with this email owns it in their personal account. For paths that
    still carry the owner's email (blueprints, kits, the clean-up script) until their data moves into
    accounts (KAN-80)."""
    from src.accounts.models import personal_account_id

    identity = IdentityRepository().find_by_email(owner_email)
    if identity is None:
        return None
    kb = (repository or KnowledgeBaseRepository()).find_in_account(personal_account_id(identity.user_id), kb_id)
    return kb if kb and kb.owner_id == identity.user_id else None


def _resolve(account_id: str, kb_id: str) -> Optional[ResourceRef]:
    kb = KnowledgeBaseRepository().find_in_account(account_id, kb_id)
    return kb.resource_ref if kb and kb.status != KnowledgeBaseStatus.DELETED else None


RESOLVERS["knowledge-base"] = _resolve
