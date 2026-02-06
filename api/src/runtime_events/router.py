"""API endpoints for querying runtime events (debug/timeline)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer

from src.agents.repository import AgentRepository
from src.runtime_events.repository import RuntimeEventRepository
from src.runtime_events.models import RuntimeEventPage

security = HTTPBearer()

router = APIRouter(
    prefix="/agents/{agent_id}/conversations/{conversation_id}/runtime-events",
    tags=["runtime-events"],
    dependencies=[Depends(security)],
)


def get_agent_repository() -> AgentRepository:
    return AgentRepository()


def get_runtime_event_repository() -> RuntimeEventRepository:
    return RuntimeEventRepository()


@router.get("", response_model=RuntimeEventPage)
async def list_runtime_events(
    request: Request,
    agent_id: str,
    conversation_id: str,
    actor_id: str = Query(..., description="Actor/user id scope for event log"),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    oldest_first: bool = Query(True),
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)] = None,  # type: ignore
    events_repo: Annotated[RuntimeEventRepository, Depends(get_runtime_event_repository)] = None,  # type: ignore
) -> RuntimeEventPage:
    """List runtime events for a conversation + actor.

    Auth: only agent owner can read.
    """
    owner_email: str = request.state.user_email

    agent = agent_repo.find_agent_by_id(agent_id, owner_email)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return events_repo.list_for_conversation(
        agent_id=agent_id,
        conversation_id=conversation_id,
        actor_id=actor_id,
        limit=limit,
        cursor=cursor,
        oldest_first=oldest_first,
    )
