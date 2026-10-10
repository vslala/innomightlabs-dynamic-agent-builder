from __future__ import annotations

import logging
from typing import Annotated

import src.form_models as form_models
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer

from src.agents.access import owner_of, require_agent
from src.agents.repository import AgentRepository
from src.accounts.owner import Owner
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.settings.access import MANAGE_SETTINGS
from src.skills.models import (
    InstallSkillRequest,
    InstalledSkillResponse,
    SkillCatalogItemResponse,
    UpdateInstalledSkillRequest,
)
from src.skills.service import SkillService, get_skill_service

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
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[SkillCatalogItemResponse]:
    return service.list_catalog(principal.account_id)


@router.get("/skills/{skill_id}/install-schema", response_model=form_models.Form, response_model_exclude_none=True)
async def get_skill_install_schema(
    skill_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> form_models.Form:
    try:
        return service.get_install_schema(
            skill_id=skill_id,
            submit_path=f"/agents/{{agent_id}}/skills?skill_id={skill_id}",
            owner=owner,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/agents/{agent_id}/skills", response_model=list[InstalledSkillResponse])
async def list_installed_skills(
    agent_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> list[InstalledSkillResponse]:
    require_agent(principal, agent_id, "agents:Get", agent_repo)
    return service.list_installed(agent_id)


@router.post("/agents/{agent_id}/skills", response_model=InstalledSkillResponse, status_code=status.HTTP_201_CREATED)
async def install_skill_for_agent(
    agent_id: str,
    body: InstallSkillRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    skill_id: str = Query(..., description="Skill id to install"),
) -> InstalledSkillResponse:
    agent = require_agent(principal, agent_id, "skills:Install", agent_repo)

    try:
        # Skills run as the agent's owner, on their account's credentials
        installed = service.install_skill(
            agent_id=agent_id,
            skill_id=skill_id,
            owner=owner_of(agent),
            raw_config=body.config,
            installed_by=principal.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return service.to_installed_response(installed)


@router.patch("/agents/{agent_id}/skills/{skill_id}", response_model=InstalledSkillResponse)
async def update_installed_skill(
    agent_id: str,
    skill_id: str,
    body: UpdateInstalledSkillRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
) -> InstalledSkillResponse:
    agent = require_agent(principal, agent_id, "skills:Configure", agent_repo)

    try:
        installed = service.update_installed(
            agent_id=agent_id,
            installed_skill_id=skill_id,
            owner=owner_of(agent),
            enabled=body.enabled,
            raw_config=body.config,
            available_to=body.available_to,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return service.to_installed_response(installed)


@router.delete("/agents/{agent_id}/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_skill(
    agent_id: str,
    skill_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SkillService, Depends(get_skill_service)],
    disconnect_oauth: bool = Query(False, description="Also delete the account's OAuth connection to this skill's provider"),
) -> None:
    agent = require_agent(principal, agent_id, "skills:Uninstall", agent_repo)
    if disconnect_oauth:
        # The connection is the account's, used by every member's agents
        principal.require(MANAGE_SETTINGS)

    service.uninstall(
        agent_id=agent_id,
        installed_skill_id=skill_id,
        owner=owner_of(agent),
        disconnect_oauth=disconnect_oauth,
    )
