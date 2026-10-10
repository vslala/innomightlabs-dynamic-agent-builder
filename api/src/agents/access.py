"""Reaching an agent from a dashboard request: find it in the caller's account, then check the action.
See docs/LLD-shared-accounts-and-iam.md, "Enforcement in routes".
"""

from typing import Annotated, Callable, Optional

from fastapi import Depends, HTTPException

from src.accounts.owner import Owner
from src.agents.models import Agent, AgentAccess
from src.agents.repository import AgentRepository
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_principal
from src.iam.principal import Principal, load_principal
from src.iam.service import IamError
from src.iam.shares import RESOLVERS
from src.identity import IdentityRepository


def require_agent(principal: Principal, agent_id: str, action: str,
                  repository: Optional[AgentRepository] = None) -> Agent:
    """The agent, if the caller may `action` it: 404 when they can't even see it, 403 when they can."""
    agent = (repository or AgentRepository()).find_in_account(principal.account_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    principal.require(action, agent.resource_ref)
    return agent


def agent_with(action: str) -> Callable[..., Agent]:
    """A route dependency: the path's agent, once the caller may `action` it."""

    def dependency(agent_id: str, principal: Annotated[Principal, Depends(get_principal)]) -> Agent:
        return require_agent(principal, agent_id, action)

    return dependency


def own_agent_with(action: str) -> Callable[..., Agent]:
    """As `agent_with`, for the caller's own agents only (see `require_own_agent`)."""

    def dependency(agent_id: str, principal: Annotated[Principal, Depends(get_principal)]) -> Agent:
        return require_own_agent(principal, agent_id, action)

    return dependency


def require_own_agent(principal: Principal, agent_id: str, action: str,
                      repository: Optional[AgentRepository] = None) -> Agent:
    """As `require_agent`, and the caller must own it: for connecting the owner's own accounts (skill
    OAuth, MCP connections) to the agent, which runs on the owner's credentials."""
    agent = require_agent(principal, agent_id, action, repository)
    if agent.owner_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Only the agent's owner can connect their own accounts to it")
    return agent


def access_to(principal: Principal, agent: Agent) -> Optional[AgentAccess]:
    """How the caller reaches the agent, or None when they can't see it."""
    if agent.owner_id == principal.user_id:
        return "owner"
    if not principal.can("agents:Describe", agent.resource_ref).allowed:
        return None
    return "shared" if principal.can("agents:Get", agent.resource_ref).allowed else "admin"


def visible_agents(principal: Principal, repository: Optional[AgentRepository] = None) -> list[tuple[Agent, AgentAccess]]:
    """The account's agents the caller can see: their own, those shared with them, and (for admins)
    everyone else's as metadata."""
    visible = []
    for agent in (repository or AgentRepository()).list_in_account(principal.account_id):
        access = access_to(principal, agent)
        if access:
            visible.append((agent, access))
    return visible


def owner_of(agent: Agent) -> Owner:
    """The member an agent acts as: whoever uses it, it runs on its owner's settings and connections."""
    identity = IdentityRepository().get(agent.owner_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return Owner(account_id=agent.account_id, user_id=agent.owner_id, email=identity.email)


def usable_agent(owner: Owner, agent_id: str, repository: Optional[AgentRepository] = None) -> Optional[Agent]:
    """The agent, if this member may chat with it in their account: their own, or one shared with them.
    For what acts as a member without a request (automations, schedules); the agent still runs as its
    own owner (`owner_of`)."""
    agent = (repository or AgentRepository()).find_in_account(owner.account_id, agent_id)
    if agent is None or agent.owner_id == owner.user_id:
        return agent
    try:
        member = load_principal(owner.user_id, owner.account_id)
    except IamError:  # they have left the account
        return None
    return agent if member.can("agents:Chat", agent.resource_ref).allowed else None


def owned_agent(agent_id: str, owner_email: str, repository: Optional[AgentRepository] = None) -> Optional[Agent]:
    """The agent, if it belongs to the person with this email, whatever account it's in. For paths that
    still carry the owner's email (background jobs, skills, automations) until their data moves into
    accounts (KAN-80)."""
    agent = (repository or AgentRepository()).get(agent_id)
    if agent is None:
        return None
    identity = IdentityRepository().find_by_email(owner_email)
    return agent if identity and agent.owner_id == identity.user_id else None


def _resolve(account_id: str, agent_id: str) -> Optional[ResourceRef]:
    agent = AgentRepository().find_in_account(account_id, agent_id)
    return agent.resource_ref if agent else None


RESOLVERS["agent"] = _resolve
