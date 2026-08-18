from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from src.a2a.auth import get_a2a_client
from src.a2a.models import (
    A2AAgentCard,
    A2AAgentListResponse,
    A2AErrorCode,
    A2AErrorResponse,
    A2AMessageSendRequest,
    A2ATaskListResponse,
    A2ATaskResponse,
)
from src.a2a.service import (
    A2ADiscoveryService,
    A2AInvocationService,
    get_a2a_discovery_service,
    get_a2a_invocation_service,
)
from src.apikeys.models import AgentApiKey

router = APIRouter(tags=["a2a"])
A2A_JSON_MEDIA_TYPE = "application/a2a+json"


@router.get("/.well-known/agent-card.json", response_model=A2AAgentCard)
async def get_facilitator_agent_card(
    service: Annotated[A2ADiscoveryService, Depends(get_a2a_discovery_service)],
) -> A2AAgentCard:
    """Return the public A2A facilitator Agent Card."""
    return service.facilitator_card()


@router.get("/a2a/agents", response_model=A2AAgentListResponse)
async def list_a2a_agents(
    service: Annotated[A2ADiscoveryService, Depends(get_a2a_discovery_service)],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
) -> A2AAgentListResponse:
    """List agents enabled for Agent2Agent discovery."""
    return service.list_agents(limit=limit, cursor=cursor)


@router.get("/a2a/agents/{agent_id}/agent-card", response_model=A2AAgentCard)
async def get_agent_card(
    agent_id: str,
    service: Annotated[A2ADiscoveryService, Depends(get_a2a_discovery_service)],
) -> A2AAgentCard:
    """Return an agent-scoped Agent Card for an A2A-enabled agent."""
    card = service.agent_card(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail="Agent not found")
    return card


@router.post("/a2a/agents/{agent_id}/message:send")
async def send_a2a_message(
    agent_id: str,
    body: A2AMessageSendRequest,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
):
    """Send a text-only A2A message to an enabled agent and return the completed task."""
    try:
        response = await service.send_message(agent_id=agent_id, request=body, api_key=api_key)
    except ValueError as exc:
        return _a2a_error(A2AErrorCode.INVALID_REQUEST, str(exc), status_code=400)
    return JSONResponse(
        content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type=A2A_JSON_MEDIA_TYPE,
    )


@router.post("/a2a/agents/{agent_id}/message:stream")
async def stream_a2a_message(
    agent_id: str,
    body: A2AMessageSendRequest,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
):
    """Send a text-only A2A message to an enabled agent and stream task status events."""
    try:
        stream = service.stream_message(agent_id=agent_id, request=body, api_key=api_key)
    except ValueError as exc:
        return _a2a_error(A2AErrorCode.INVALID_REQUEST, str(exc), status_code=400)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/a2a/agents/{agent_id}/tasks", response_model=A2ATaskListResponse)
async def list_a2a_tasks(
    agent_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
) -> A2ATaskListResponse:
    """List A2A tasks for this agent and API key."""
    return A2ATaskListResponse(items=service.list_tasks(agent_id=agent_id, api_key=api_key))


@router.post("/a2a/agents/{agent_id}/tasks/{task_id}:cancel")
async def cancel_a2a_task(
    agent_id: str,
    task_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
):
    """Cancellation is part of the A2A surface but is not implemented in v1."""
    return _a2a_error(
        A2AErrorCode.UNSUPPORTED_OPERATION,
        "Task cancellation is not supported yet",
        status_code=501,
    )


@router.post("/a2a/agents/{agent_id}/tasks/{task_id}:subscribe")
async def subscribe_a2a_task(
    agent_id: str,
    task_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
):
    """Durable task subscription is part of the A2A surface but is not implemented in v1."""
    return _a2a_error(
        A2AErrorCode.UNSUPPORTED_OPERATION,
        "Task subscription is not supported yet",
        status_code=501,
    )


@router.get("/a2a/agents/{agent_id}/tasks/{task_id}", response_model=A2ATaskResponse)
async def get_a2a_task(
    agent_id: str,
    task_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_a2a_client)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
) -> A2ATaskResponse:
    """Get a persisted A2A task if it belongs to this API key."""
    task = service.get_task(agent_id=agent_id, task_id=task_id, api_key=api_key)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return A2ATaskResponse(task=task)


def _a2a_error(code: A2AErrorCode, message: str, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=A2AErrorResponse(code=code, message=message).model_dump(mode="json"),
        media_type=A2A_JSON_MEDIA_TYPE,
    )
