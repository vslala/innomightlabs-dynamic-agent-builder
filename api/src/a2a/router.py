from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.a2a.auth import get_agent_repository, get_api_key_repository, require_a2a_client
from src.a2a.models import (
    A2AAgentCard,
    A2AAgentListResponse,
    A2AErrorCode,
    A2AErrorResponse,
    A2AMessageSendRequest,
    A2ATaskListResponse,
    A2ATaskResponse,
)
from src.a2a.oauth import (
    A2A_SCOPE_MESSAGE,
    A2A_SCOPE_TASKS,
    bearer_challenge,
    issue_a2a_access_token,
    oauth_metadata,
    parse_client_credentials_request,
    validate_client_credentials,
)
from src.a2a.service import (
    A2ADiscoveryService,
    A2AInvocationService,
    get_a2a_discovery_service,
    get_a2a_invocation_service,
)
from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.agents.repository import AgentRepository

router = APIRouter(tags=["a2a"])
A2A_JSON_MEDIA_TYPE = "application/a2a+json"
JSON_RPC_VERSION = "2.0"
A2A_MESSAGE_CLIENT = require_a2a_client({A2A_SCOPE_MESSAGE})
A2A_TASK_CLIENT = require_a2a_client({A2A_SCOPE_TASKS})
A2A_JSONRPC_CLIENT = require_a2a_client({A2A_SCOPE_MESSAGE, A2A_SCOPE_TASKS})


@router.get("/a2a/oauth/.well-known/oauth-authorization-server")
async def get_a2a_oauth_metadata() -> dict[str, Any]:
    """Return OAuth 2.0 authorization server metadata for A2A clients."""
    return oauth_metadata()


@router.post("/a2a/oauth/token")
async def issue_a2a_oauth_token(
    request: Request,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> JSONResponse:
    """Issue a scoped A2A access token using OAuth 2.0 client credentials."""
    credentials = await parse_client_credentials_request(request)
    api_key = validate_client_credentials(credentials=credentials, api_key_repo=api_key_repo)
    agent = agent_repo.find_agent_by_id(api_key.agent_id, api_key.created_by)
    if not agent or not agent.is_agent2agent_enabled:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_client", "error_description": "A2A agent is not enabled"},
            headers=bearer_challenge(error="invalid_client"),
        )
    token = issue_a2a_access_token(api_key=api_key, requested_scope=credentials.scope)
    return JSONResponse(
        content=token,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.get(
    "/a2a/agents",
    response_model=A2AAgentListResponse,
    response_model_exclude_none=True,
)
async def list_a2a_agents(
    service: Annotated[A2ADiscoveryService, Depends(get_a2a_discovery_service)],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
) -> A2AAgentListResponse:
    """List agents enabled for Agent2Agent discovery."""
    return service.list_agents(limit=limit, cursor=cursor)


@router.get(
    "/a2a/agents/{agent_id}/card",
    response_model=A2AAgentCard,
    response_model_exclude_none=True,
)
async def get_agent_card(
    agent_id: str,
    service: Annotated[A2ADiscoveryService, Depends(get_a2a_discovery_service)],
) -> A2AAgentCard:
    """Return an agent-scoped Agent Card for an A2A-enabled agent."""
    card = service.agent_card(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail="Agent not found")
    return card


@router.post("/a2a/agents/{agent_id}")
async def handle_a2a_jsonrpc(
    agent_id: str,
    body: dict[str, Any],
    api_key: Annotated[AgentApiKey, Depends(A2A_JSONRPC_CLIENT)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
):
    """Primary A2A JSON-RPC endpoint for one agent."""
    request_id = body.get("id")
    method = str(body.get("method") or "").strip()
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    if body.get("jsonrpc") != JSON_RPC_VERSION:
        return _jsonrpc_error(request_id, -32600, "Invalid JSON-RPC version")

    try:
        if method == "SendMessage":
            request = A2AMessageSendRequest.model_validate(params)
            response = await service.send_message(agent_id=agent_id, request=request, api_key=api_key)
            return _jsonrpc_result(request_id, {"task": _sdk_task(response.task)})
        if method == "GetTask":
            task_id = str(params.get("id") or params.get("taskId") or "").strip()
            if not task_id:
                return _jsonrpc_error(request_id, -32602, "GetTask requires id")
            task = service.get_task(agent_id=agent_id, task_id=task_id, api_key=api_key)
            if not task:
                return _jsonrpc_error(request_id, -32004, "Task not found")
            return _jsonrpc_result(request_id, _sdk_task(task))
        if method == "ListTasks":
            tasks = service.list_tasks(agent_id=agent_id, api_key=api_key)
            return _jsonrpc_result(request_id, {"tasks": [_sdk_task(task) for task in tasks]})
        if method in {"CancelTask", "SubscribeToTask"}:
            return _jsonrpc_error(request_id, -32001, f"{method} is not supported yet")
    except ValueError as exc:
        return _jsonrpc_error(request_id, -32602, str(exc))

    return _jsonrpc_error(request_id, -32601, f"Unsupported A2A method: {method}")


@router.post("/a2a/agents/{agent_id}/message:send")
async def send_a2a_message(
    agent_id: str,
    body: A2AMessageSendRequest,
    api_key: Annotated[AgentApiKey, Depends(A2A_MESSAGE_CLIENT)],
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
    api_key: Annotated[AgentApiKey, Depends(A2A_MESSAGE_CLIENT)],
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
    api_key: Annotated[AgentApiKey, Depends(A2A_TASK_CLIENT)],
    service: Annotated[A2AInvocationService, Depends(get_a2a_invocation_service)],
) -> A2ATaskListResponse:
    """List A2A tasks for this agent and API key."""
    return A2ATaskListResponse(items=service.list_tasks(agent_id=agent_id, api_key=api_key))


@router.post("/a2a/agents/{agent_id}/tasks/{task_id}:cancel")
async def cancel_a2a_task(
    agent_id: str,
    task_id: str,
    api_key: Annotated[AgentApiKey, Depends(A2A_TASK_CLIENT)],
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
    api_key: Annotated[AgentApiKey, Depends(A2A_TASK_CLIENT)],
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
    api_key: Annotated[AgentApiKey, Depends(A2A_TASK_CLIENT)],
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


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content={"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result},
        media_type="application/json",
    )


def _jsonrpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        content={
            "jsonrpc": JSON_RPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        },
        media_type="application/json",
    )


def _sdk_task(task) -> dict[str, Any]:
    payload = {
        "id": task.task_id,
        "contextId": task.context_id,
        "status": {
            "state": task.status.state.value,
        },
        "history": [_sdk_message(message) for message in task.history],
    }
    if task.status.message:
        payload["status"]["message"] = _sdk_message(task.status.message)
    return payload


def _sdk_message(message) -> dict[str, Any]:
    payload = {
        "messageId": message.message_id,
        "role": message.role.value,
        "parts": [{"text": part.text} for part in message.parts],
    }
    if message.task_id:
        payload["taskId"] = message.task_id
    if message.context_id:
        payload["contextId"] = message.context_id
    return payload
