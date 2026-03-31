from __future__ import annotations

import logging
from typing import Annotated

import src.form_models as form_models
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.agents.repository import AgentRepository
from src.skills.models import (
    InstallSkillRequest,
    InstalledSkillResponse,
    SkillCatalogItemResponse,
    UpdateInstalledSkillRequest,
)
from src.skills.service import SkillService, get_skill_service
from src.common.pagination import Paginated


class SearchSelectOption(BaseModel):
    """Option item for search_select style inputs."""

    value: str
    label: str
    description: str | None = None

log = logging.getLogger(__name__)

security = HTTPBearer()

router = APIRouter(
    tags=["skills"],
    dependencies=[Depends(security)],
)


def get_agent_repository() -> AgentRepository:
    return AgentRepository()


@router.get("/skills", response_model=list[SkillCatalogItemResponse])
async def list_skills(
    request: Request,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[SkillCatalogItemResponse]:
    user_email: str = request.state.user_email
    return service.list_catalog(user_email)


@router.get("/skills/{skill_id}/install-schema", response_model=form_models.Form, response_model_exclude_none=True)
async def get_skill_install_schema(
    skill_id: str,
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> form_models.Form:
    try:
        return service.get_install_schema(
            skill_id=skill_id,
            submit_path=f"/agents/{{agent_id}}/skills?skill_id={skill_id}",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/skills/search-options/agents", response_model=Paginated[SearchSelectOption])
async def search_agent_options(
    request: Request,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> Paginated[SearchSelectOption]:
    """Search agents and return results as search-select options.

    This is a *skills/forms* convenience endpoint. It delegates to the same underlying
    repository search logic used by `/agents/search` but returns the option shape:
    - value = agent_id
    - label = agent_name
    - description = agent_description (if available)
    """

    # Reuse /agents/search logic by calling repository directly (same filtering/sorting/cursor pattern)
    import base64
    import json

    user_email: str = request.state.user_email
    agents = agent_repo.find_all_by_created_by(user_email)

    query = (q or "").strip().lower()
    if query:
        def matches(agent) -> bool:
            name = (getattr(agent, "agent_name", "") or "").lower()
            desc = (getattr(agent, "agent_description", None) or "").lower()
            return query in name or query in desc

        agents = [a for a in agents if matches(a)]

    agents.sort(key=lambda a: (getattr(a, "agent_name", "") or "").lower())

    offset = 0
    if cursor:
        try:
            cursor_data = json.loads(base64.b64decode(cursor).decode("utf-8"))
            offset = int(cursor_data.get("offset", 0))
        except Exception:
            offset = 0

    page = agents[offset: offset + limit]
    has_more = len(agents) > offset + limit

    next_cursor = None
    if has_more:
        next_cursor = base64.b64encode(json.dumps({"offset": offset + limit}).encode("utf-8")).decode("utf-8")

    items = [
        SearchSelectOption(
            value=a.agent_id,
            label=a.agent_name,
            description=getattr(a, "agent_description", None),
        )
        for a in page
    ]

    return Paginated[SearchSelectOption](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=len(agents),
    )


@router.get("/agents/{agent_id}/skills", response_model=list[InstalledSkillResponse])
async def list_installed_skills(
    request: Request,
    agent_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[InstalledSkillResponse]:
    user_email: str = request.state.user_email
    agent = agent_repo.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return service.list_installed(agent_id)


@router.post("/agents/{agent_id}/skills", response_model=InstalledSkillResponse, status_code=status.HTTP_201_CREATED)
async def install_skill_for_agent(
    request: Request,
    agent_id: str,
    body: InstallSkillRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    skill_id: str = Query(..., description="Skill id to install"),
) -> InstalledSkillResponse:
    user_email: str = request.state.user_email
    agent = agent_repo.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        installed = service.install_skill(
            agent_id=agent_id,
            skill_id=skill_id,
            user_email=user_email,
            raw_config=body.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return InstalledSkillResponse(
        skill_id=installed.skill_id,
        namespace=installed.namespace,
        name=installed.skill_name,
        description=installed.skill_description,
        enabled=installed.enabled,
        installed_at=installed.installed_at,
        updated_at=installed.updated_at,
        config=installed.config,
        secret_fields=installed.secret_fields,
    )


@router.patch("/agents/{agent_id}/skills/{skill_id}", response_model=InstalledSkillResponse)
async def update_installed_skill(
    request: Request,
    agent_id: str,
    skill_id: str,
    body: UpdateInstalledSkillRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> InstalledSkillResponse:
    user_email: str = request.state.user_email
    agent = agent_repo.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        installed = service.update_installed(
            agent_id=agent_id,
            skill_id=skill_id,
            enabled=body.enabled,
            raw_config=body.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return InstalledSkillResponse(
        skill_id=installed.skill_id,
        namespace=installed.namespace,
        name=installed.skill_name,
        description=installed.skill_description,
        enabled=installed.enabled,
        installed_at=installed.installed_at,
        updated_at=installed.updated_at,
        config=installed.config,
        secret_fields=installed.secret_fields,
    )


@router.delete("/agents/{agent_id}/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_skill(
    request: Request,
    agent_id: str,
    skill_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> None:
    user_email: str = request.state.user_email
    agent = agent_repo.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    service.uninstall(agent_id, skill_id)
