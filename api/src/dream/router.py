"""Authenticated configuration and observability API for Dream."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.agents.repository import AgentRepository
from src.dream.models import DreamSettings, DreamSettingsRequest
from src.dream.repository import DreamRepository, get_dream_repository
from src.dream.schemas import build_dream_settings_form
from src.dream.service import DreamService, get_dream_service
from src.form_models import Form
from src.form_options import FormOptionsContext, hydrate_form_options, validate_form_options
from src.scheduler.cron import ScheduleExpression, ScheduleExpressionError, validate_schedule_expression
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

security = HTTPBearer()
router = APIRouter(tags=["dream"], dependencies=[Depends(security)])


def _agent_or_404(agent_id: str, user_email: str) -> None:
    if AgentRepository().find_agent_by_id(agent_id, user_email) is None:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/dream/settings", response_model=DreamSettings | None)
async def get_settings(
    request: Request,
    repository: Annotated[DreamRepository, Depends(get_dream_repository)],
) -> DreamSettings | None:
    return repository.find_settings(request.state.user_email)


@router.get("/dream/settings/forms/configure", response_model=Form, response_model_exclude_none=True)
async def get_settings_form(
    request: Request,
    repository: Annotated[DreamRepository, Depends(get_dream_repository)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> Form:
    return hydrate_form_options(
        build_dream_settings_form(repository.find_settings(request.state.user_email)),
        FormOptionsContext(user_email=request.state.user_email, provider_settings_repository=provider_settings_repository),
    )


@router.put("/dream/settings", response_model=DreamSettings)
async def save_settings(
    request: Request,
    body: DreamSettingsRequest,
    repository: Annotated[DreamRepository, Depends(get_dream_repository)],
    service: Annotated[DreamService, Depends(get_dream_service)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> DreamSettings:
    try:
        validate_schedule_expression(ScheduleExpression(body.cron_expression, body.timezone))
        validate_form_options(
            build_dream_settings_form().form_inputs,
            {"enabled": str(body.enabled).lower(), "provider_name": body.provider_name or "", "model_name": body.model_name or ""},
            FormOptionsContext(user_email=request.state.user_email, provider_settings_repository=provider_settings_repository),
        )
    except (ScheduleExpressionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    dream_settings = DreamSettings(user_email=request.state.user_email, **body.model_dump())
    saved = repository.save_settings(dream_settings)
    for agent in AgentRepository().find_all_by_created_by(request.state.user_email):
        if agent.agent_architecture == "krishna-memgpt":
            service.ensure_schedule(agent.agent_id, request.state.user_email, request.state.user_email, saved)
    return saved


@router.get("/agents/{agent_id}/dream/runs")
async def list_runs(
    agent_id: str, request: Request, repository: Annotated[DreamRepository, Depends(get_dream_repository)], limit: int = 20
):
    _agent_or_404(agent_id, request.state.user_email)
    return repository.list_runs(agent_id, request.state.user_email, max(1, min(limit, 100)))


@router.get("/agents/{agent_id}/dream/runs/{run_id}/actions")
async def list_actions(
    agent_id: str, run_id: str, request: Request, repository: Annotated[DreamRepository, Depends(get_dream_repository)]
):
    _agent_or_404(agent_id, request.state.user_email)
    if not any(run.run_id == run_id for run in repository.list_runs(agent_id, request.state.user_email, 100)):
        raise HTTPException(status_code=404, detail="Dream run not found")
    return repository.list_action_logs(run_id)


@router.get("/agents/{agent_id}/dream/cursor")
async def get_cursor(agent_id: str, request: Request, repository: Annotated[DreamRepository, Depends(get_dream_repository)]):
    _agent_or_404(agent_id, request.state.user_email)
    return repository.find_cursor(agent_id, request.state.user_email)


@router.post("/agents/{agent_id}/dream/run", status_code=status.HTTP_202_ACCEPTED)
async def run_now(
    agent_id: str, request: Request, background_tasks: BackgroundTasks,
    service: Annotated[DreamService, Depends(get_dream_service)],
):
    _agent_or_404(agent_id, request.state.user_email)
    background_tasks.add_task(
        service.dream, agent_id=agent_id, user_id=request.state.user_email,
        owner_email=request.state.user_email, mode="manual",
    )
    return {"status": "accepted"}
