"""Automations API router."""

import asyncio
import json
import logging
from typing import Annotated, Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from src.automations.models import (
    AutomationGraphResponse,
    AutomationActionCatalogResponse,
    AutomationResponse,
    AutomationSkillResponse,
    AutomationRunDetailResponse,
    AutomationRunResponse,
    AutomationNodeResponse,
    AutomationEdgeResponse,
    AutomationTriggerResponse,
    AutomationTriggerType,
    CreateAutomationEdgeRequest,
    CreateAutomationNodeRequest,
    CreateAutomationRequest,
    CreateAutomationTriggerRequest,
    EnableAutomationSkillRequest,
    SaveAutomationGraphRequest,
    StartAutomationRunRequest,
    UpdateAutomationEdgeRequest,
    UpdateAutomationSkillRequest,
    UpdateAutomationNodeRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.triggers.schemas import build_manual_trigger_form, build_schedule_trigger_form
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.automations.run_state import AutomationRunStateService
from src.automations.service import (
    AutomationNotFoundError,
    AutomationService,
    AutomationValidationError,
)
from src.common.pagination import Paginated
from src.config import settings
from src.form_models import Form

log = logging.getLogger(__name__)

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


def invoke_automation_run_async(run_id: str, automation_id: str, user_email: str) -> None:
    if settings.async_job_backend != "lambda":
        log.info("Automation run will execute in local background task: %s", run_id)
        asyncio.create_task(AutomationRunner().execute_run(run_id, user_email))
        return

    function_name = settings.async_job_lambda_name
    if not function_name:
        raise AutomationValidationError("ASYNC_JOB_LAMBDA_NAME is required when ASYNC_JOB_BACKEND=lambda")

    client = boto3.client("lambda", region_name=settings.aws_region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "automation_run": {
                    "run_id": run_id,
                    "automation_id": automation_id,
                    "user_email": user_email,
                }
            }
        ).encode("utf-8"),
    )
    log.info("Invoked Lambda async for automation run %s, status: %s", run_id, response["StatusCode"])


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


@router.get("/{automation_id}/action-catalog", response_model=AutomationActionCatalogResponse)
async def get_action_catalog(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationActionCatalogResponse:
    try:
        return service.list_action_catalog(automation_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/skills", response_model=list[AutomationSkillResponse])
async def list_automation_skills(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> list[AutomationSkillResponse]:
    try:
        return service.list_skills(automation_id, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/skills", response_model=AutomationSkillResponse, status_code=201)
async def enable_automation_skill(
    request: Request,
    automation_id: str,
    body: EnableAutomationSkillRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    skill_id: str = Query(..., description="Skill id to enable"),
) -> AutomationSkillResponse:
    try:
        return service.enable_skill(automation_id, skill_id, body, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/skills/{skill_id}", response_model=AutomationSkillResponse)
async def update_automation_skill(
    request: Request,
    automation_id: str,
    skill_id: str,
    body: UpdateAutomationSkillRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationSkillResponse:
    try:
        return service.update_skill(automation_id, skill_id, body, get_user_email(request))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/skills/{skill_id}", status_code=204)
async def delete_automation_skill(
    request: Request,
    automation_id: str,
    skill_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_skill(automation_id, skill_id, get_user_email(request))
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


@router.get("/{automation_id}/triggers", response_model=list[AutomationTriggerResponse])
async def list_triggers(
    request: Request,
    automation_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> list[AutomationTriggerResponse]:
    try:
        triggers = service.list_triggers(automation_id, get_user_email(request))
        return [trigger.to_response() for trigger in triggers]
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/triggers/forms/{trigger_type}", response_model=Form)
async def get_trigger_form(
    request: Request,
    automation_id: str,
    trigger_type: AutomationTriggerType,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> Form:
    try:
        graph = service.get_graph(automation_id, get_user_email(request))
        submit_path = f"/automations/{automation_id}/triggers"
        if trigger_type == AutomationTriggerType.SCHEDULE:
            return build_schedule_trigger_form(graph.nodes, submit_path=submit_path)
        if trigger_type == AutomationTriggerType.MANUAL:
            return build_manual_trigger_form(graph.nodes, submit_path=submit_path)
        raise AutomationValidationError(f"Unsupported trigger form type: {trigger_type.value}")
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


@router.post(
    "/{automation_id}/test-run",
    response_model=AutomationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
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
        run = runner.create_test_run(graph, body.trigger_id, body.input, user_email)
        invoke_automation_run_async(run.run_id, automation_id, user_email)
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
        run_state = AutomationRunStateService(repo)
        runs = [run_state.fail_if_stale(run) for run in runs]
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
        run = AutomationRunStateService(repo).fail_if_stale(run)
        return AutomationRunDetailResponse(
            run=run.to_response(),
            context=run.context,
            node_results=[
                result.to_response() for result in repo.find_node_results(run.run_id)
            ],
        )
    except Exception as exc:
        raise translate_error(exc) from exc
