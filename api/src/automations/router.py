"""Automations API router."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from src.automations.models import (
    AutomationGraphResponse,
    AutomationResponse,
    AutomationRunDetailResponse,
    AutomationRunResponse,
    AutomationNodeResponse,
    AutomationEdgeResponse,
    AutomationTriggerResponse,
    CreateAutomationEdgeRequest,
    CreateAutomationNodeRequest,
    CreateAutomationRequest,
    CreateAutomationTriggerRequest,
    SaveAutomationGraphRequest,
    StartAutomationRunRequest,
    UpdateAutomationEdgeRequest,
    UpdateAutomationNodeRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.automations.service import (
    AutomationNotFoundError,
    AutomationService,
    AutomationValidationError,
)
from src.common.pagination import Paginated

security = HTTPBearer()

router = APIRouter(
    prefix="/automations",
    tags=["automations"],
    dependencies=[Depends(security)],
)


def get_automation_repository() -> AutomationRepository:
    return AutomationRepository()


def get_automation_service(
    repo: Annotated[AutomationRepository, Depends(get_automation_repository)],
) -> AutomationService:
    return AutomationService(repo=repo)


def get_automation_runner(
    repo: Annotated[AutomationRepository, Depends(get_automation_repository)],
) -> AutomationRunner:
    return AutomationRunner(automation_repo=repo)


def get_user_email(request: Request) -> str:
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return str(user_email)


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AutomationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AutomationValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Automation operation failed")


@router.post("", response_model=AutomationGraphResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    request: Request,
    body: CreateAutomationRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    try:
        return service.create_automation(body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("", response_model=list[AutomationResponse])
async def list_automations(
    request: Request,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> list[AutomationResponse]:
    return [item.to_response() for item in service.list_automations(get_user_email(request))]


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationResponse:
    try:
        return service.get_automation(automation_id, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    request: Request,
    automation_id: str,
    body: UpdateAutomationRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationResponse:
    try:
        return service.update_automation(automation_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_automation(automation_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/graph", response_model=AutomationGraphResponse)
async def get_graph(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    try:
        return service.get_graph(automation_id, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.put("/{automation_id}/graph", response_model=AutomationGraphResponse)
async def save_graph(
    request: Request,
    automation_id: str,
    body: SaveAutomationGraphRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    try:
        return service.save_graph(automation_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/nodes", response_model=AutomationNodeResponse, status_code=201)
async def add_node(
    request: Request,
    automation_id: str,
    body: CreateAutomationNodeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationNodeResponse:
    try:
        return service.add_node(automation_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/nodes/{node_id}", response_model=AutomationNodeResponse)
async def update_node(
    request: Request,
    automation_id: str,
    node_id: str,
    body: UpdateAutomationNodeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationNodeResponse:
    try:
        return service.update_node(automation_id, node_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/nodes/{node_id}", status_code=204)
async def delete_node(
    request: Request,
    automation_id: str,
    node_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_node(automation_id, node_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/edges", response_model=AutomationEdgeResponse, status_code=201)
async def add_edge(
    request: Request,
    automation_id: str,
    body: CreateAutomationEdgeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationEdgeResponse:
    try:
        return service.add_edge(automation_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/edges/{edge_id}", response_model=AutomationEdgeResponse)
async def update_edge(
    request: Request,
    automation_id: str,
    edge_id: str,
    body: UpdateAutomationEdgeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationEdgeResponse:
    try:
        return service.update_edge(automation_id, edge_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/edges/{edge_id}", status_code=204)
async def delete_edge(
    request: Request,
    automation_id: str,
    edge_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_edge(automation_id, edge_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/triggers", response_model=AutomationTriggerResponse, status_code=201)
async def add_trigger(
    request: Request,
    automation_id: str,
    body: CreateAutomationTriggerRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationTriggerResponse:
    try:
        return service.add_trigger(automation_id, body, get_user_email(request)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/triggers/{trigger_id}", response_model=AutomationTriggerResponse)
async def update_trigger(
    request: Request,
    automation_id: str,
    trigger_id: str,
    body: UpdateAutomationTriggerRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationTriggerResponse:
    try:
        return service.update_trigger(
            automation_id, trigger_id, body, get_user_email(request)
        ).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/triggers/{trigger_id}", status_code=204)
async def delete_trigger(
    request: Request,
    automation_id: str,
    trigger_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_trigger(automation_id, trigger_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/test-run", response_model=AutomationRunResponse)
async def test_run(
    request: Request,
    automation_id: str,
    body: StartAutomationRunRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    runner: Annotated[AutomationRunner, Depends(get_automation_runner)],
) -> AutomationRunResponse:
    user_email = get_user_email(request)
    try:
        graph = service.get_graph(automation_id, user_email)
        service.validate_graph(graph.nodes, graph.edges, graph.triggers, user_email)
        run = await runner.run_test(graph, body.trigger_id, body.input, user_email)
        return run.to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/runs", response_model=Paginated[AutomationRunResponse])
async def list_runs(
    request: Request,
    automation_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = None,
    service: AutomationService = Depends(get_automation_service),
    repo: AutomationRepository = Depends(get_automation_repository),
) -> Paginated[AutomationRunResponse]:
    try:
        service.get_automation(automation_id, get_user_email(request))
        runs, next_cursor, has_more = repo.find_runs_by_automation(automation_id, limit, cursor)
        return Paginated[AutomationRunResponse](
            items=[run.to_response() for run in runs],
            next_cursor=next_cursor,
            has_more=has_more,
        )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/runs/{run_id}", response_model=AutomationRunDetailResponse)
async def get_run(
    request: Request,
    automation_id: str,
    run_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    repo: Annotated[AutomationRepository, Depends(get_automation_repository)],
) -> AutomationRunDetailResponse:
    user_email = get_user_email(request)
    try:
        service.get_automation(automation_id, user_email)
        run = repo.find_run_by_id(run_id, user_email)
        if not run or run.automation_id != automation_id:
            raise AutomationNotFoundError("Run not found")
        return AutomationRunDetailResponse(
            run=run.to_response(),
            context=run.context,
            node_results=[
                result.to_response() for result in repo.find_node_results(run.run_id)
            ],
        )
    except Exception as exc:
        raise translate_error(exc) from exc
