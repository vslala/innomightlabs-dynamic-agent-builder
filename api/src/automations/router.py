"""Automations API router."""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from src.accounts.owner import Owner
from src.automations.dispatch import invoke_automation_run_async
from src.automations.access import access_to, automation_with, owner_of_automation, visible_automations
from src.automations.models import (
    Automation,
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
    SmartValuePreviewRequest,
    SmartValuePreviewResponse,
    StartAutomationRunRequest,
    UpdateAutomationEdgeRequest,
    UpdateAutomationSkillRequest,
    UpdateAutomationNodeRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.triggers.schemas import (
    build_lead_captured_trigger_form,
    build_manual_trigger_form,
    build_schedule_trigger_form,
)
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.automations.run_state import AutomationRunStateService
from src.automations.errors import AutomationNotFoundError, AutomationValidationError
from src.automations.service import AutomationService
from src.common.pagination import Paginated
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.agents.repository import AgentRepository
from src.form_models import Form, SelectOption
from src.leads.service import LeadsService
from src.scheduler.service import SchedulerValidationError

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


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AutomationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (AutomationValidationError, SchedulerValidationError)):
        # A schedule trigger's timing the scheduler refuses (a one-time moment already past) is the person's to fix.
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Automation operation failed")


@router.post("", response_model=AutomationGraphResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: CreateAutomationRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    owner: Annotated[Owner, Depends(get_owner)],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    """A new automation in the account the request acts in, owned by the caller."""
    principal.require("automations:Create", ResourceRef("automation"))
    try:
        return service.create_automation(body, owner).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("", response_model=list[AutomationResponse])
async def list_automations(
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[AutomationRepository, Depends(get_automation_repository)],
) -> list[AutomationResponse]:
    """The caller's automations, those shared with them, and (for admins) everyone else's."""
    return [item.to_response(access) for item, access in visible_automations(principal, repo)]


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Describe"))],
    principal: Annotated[Principal, Depends(get_principal)],
) -> AutomationResponse:
    return automation.to_response(access_to(principal, automation) or "admin")


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: UpdateAutomationRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationResponse:
    try:
        return service.update_automation(automation_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Delete"))],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_automation(automation_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/graph", response_model=AutomationGraphResponse)
async def get_graph(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    try:
        return service.get_graph(automation_id, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/action-catalog", response_model=AutomationActionCatalogResponse)
async def get_action_catalog(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationActionCatalogResponse:
    try:
        return service.list_action_catalog(automation_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/smart-values/preview", response_model=SmartValuePreviewResponse)
async def preview_smart_values(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    body: SmartValuePreviewRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> SmartValuePreviewResponse:
    try:
        return service.preview_smart_values(automation_id, body, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/skills", response_model=list[AutomationSkillResponse])
async def list_automation_skills(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> list[AutomationSkillResponse]:
    try:
        return service.list_skills(automation_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/skills", response_model=AutomationSkillResponse, status_code=201)
async def enable_automation_skill(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: EnableAutomationSkillRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    skill_id: str = Query(..., description="Skill id to enable"),
) -> AutomationSkillResponse:
    try:
        return service.enable_skill(automation_id, skill_id, body, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/skills/{skill_id}", response_model=AutomationSkillResponse)
async def update_automation_skill(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    skill_id: str,
    body: UpdateAutomationSkillRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationSkillResponse:
    try:
        return service.update_skill(automation_id, skill_id, body, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/skills/{skill_id}", status_code=204)
async def delete_automation_skill(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    skill_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_skill(automation_id, skill_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.put("/{automation_id}/graph", response_model=AutomationGraphResponse)
async def save_graph(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: SaveAutomationGraphRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationGraphResponse:
    try:
        return service.save_graph(automation_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/nodes", response_model=AutomationNodeResponse, status_code=201)
async def add_node(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: CreateAutomationNodeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationNodeResponse:
    try:
        return service.add_node(automation_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/nodes/{node_id}", response_model=AutomationNodeResponse)
async def update_node(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    node_id: str,
    body: UpdateAutomationNodeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationNodeResponse:
    try:
        return service.update_node(automation_id, node_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/nodes/{node_id}", status_code=204)
async def delete_node(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    node_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_node(automation_id, node_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/edges", response_model=AutomationEdgeResponse, status_code=201)
async def add_edge(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: CreateAutomationEdgeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationEdgeResponse:
    try:
        return service.add_edge(automation_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/edges/{edge_id}", response_model=AutomationEdgeResponse)
async def update_edge(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    edge_id: str,
    body: UpdateAutomationEdgeRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationEdgeResponse:
    try:
        return service.update_edge(automation_id, edge_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/edges/{edge_id}", status_code=204)
async def delete_edge(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    edge_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_edge(automation_id, edge_id, owner_of_automation(automation))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{automation_id}/triggers", response_model=AutomationTriggerResponse, status_code=201)
async def add_trigger(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    body: CreateAutomationTriggerRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationTriggerResponse:
    try:
        return service.add_trigger(automation_id, body, owner_of_automation(automation)).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/triggers", response_model=list[AutomationTriggerResponse])
async def list_triggers(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> list[AutomationTriggerResponse]:
    try:
        triggers = service.list_triggers(automation_id, owner_of_automation(automation))
        return [trigger.to_response() for trigger in triggers]
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/triggers/forms/{trigger_type}", response_model=Form)
async def get_trigger_form(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    trigger_type: AutomationTriggerType,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> Form:
    try:
        graph = service.get_graph(automation_id, owner_of_automation(automation))
        submit_path = f"/automations/{automation_id}/triggers"
        if trigger_type == AutomationTriggerType.SCHEDULE:
            return build_schedule_trigger_form(graph.nodes, submit_path=submit_path)
        if trigger_type == AutomationTriggerType.MANUAL:
            return build_manual_trigger_form(graph.nodes, submit_path=submit_path)
        if trigger_type == AutomationTriggerType.LEAD_CAPTURED:
            forms = LeadsService().list_forms(automation.account_id)
            agents = AgentRepository().list_in_account(automation.account_id)
            return build_lead_captured_trigger_form(
                graph.nodes,
                forms=[SelectOption(value=form.slug, label=form.name) for form in forms if form.is_active],
                agents=[SelectOption(value=agent.agent_id, label=agent.agent_name) for agent in agents],
                submit_path=submit_path,
            )
        raise AutomationValidationError(f"Unsupported trigger form type: {trigger_type.value}")
    except Exception as exc:
        raise translate_error(exc) from exc


@router.patch("/{automation_id}/triggers/{trigger_id}", response_model=AutomationTriggerResponse)
async def update_trigger(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    trigger_id: str,
    body: UpdateAutomationTriggerRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> AutomationTriggerResponse:
    try:
        return service.update_trigger(
            automation_id, trigger_id, body, owner_of_automation(automation)
        ).to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{automation_id}/triggers/{trigger_id}", status_code=204)
async def delete_trigger(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Update"))],
    trigger_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
) -> None:
    try:
        service.delete_trigger(automation_id, trigger_id, owner_of_automation(automation))
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
    automation: Annotated[Automation, Depends(automation_with("automations:Run"))],
    body: StartAutomationRunRequest,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    runner: Annotated[AutomationRunner, Depends(get_automation_runner)],
) -> AutomationRunResponse:
    owner = owner_of_automation(automation)  # whoever starts it, it runs as its owner
    try:
        graph = service.get_graph(automation_id, owner)
        service.validate_graph(graph.nodes, graph.edges, graph.triggers, owner)
        run = runner.create_test_run(graph, body.trigger_id, body.input, owner)
        invoke_automation_run_async(run.run_id, automation_id, owner)
        return run.to_response()
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{automation_id}/runs", response_model=Paginated[AutomationRunResponse])
async def list_runs(
    request: Request,
    automation_id: str,
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = None,
    service: AutomationService = Depends(get_automation_service),
    repo: AutomationRepository = Depends(get_automation_repository),
) -> Paginated[AutomationRunResponse]:
    try:
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
    automation: Annotated[Automation, Depends(automation_with("automations:Get"))],
    run_id: str,
    service: Annotated[AutomationService, Depends(get_automation_service)],
    repo: Annotated[AutomationRepository, Depends(get_automation_repository)],
) -> AutomationRunDetailResponse:
    try:
        run = repo.find_run_by_id(run_id)
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
