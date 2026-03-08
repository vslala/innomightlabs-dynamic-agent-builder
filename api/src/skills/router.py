"""
Skills API router.

Provides endpoints for:
- Listing available skills from the registry
- Loading form schema for a skill
- Enabling/disabling skills with user configuration
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from src.config import settings
from src.form_models import Form
from src.skills.config_repository import UserSkillConfigRepository
from src.skills.models import SkillRegistryEntry, UserSkillConfig
from src.skills.registry import FileSystemSkillsRegistry, SkillsRegistryInterface
from src.skills.schema_loader import parse_form_schema

log = logging.getLogger(__name__)

security = HTTPBearer()

router = APIRouter(prefix="/skills", tags=["skills"], dependencies=[Depends(security)])


# -----------------------------------------------------------------------------
# Dependency injection
# -----------------------------------------------------------------------------


def get_registry() -> SkillsRegistryInterface:
    """Create the skills registry instance from configured path."""
    root = Path(settings.skills_root)
    return FileSystemSkillsRegistry(root)


def get_config_repository() -> UserSkillConfigRepository:
    """Create the user skill config repository."""
    return UserSkillConfigRepository()


# -----------------------------------------------------------------------------
# Request / Response models
# -----------------------------------------------------------------------------


class EnableSkillRequest(BaseModel):
    """Request body for enabling a skill."""

    skill_id: str = Field(..., min_length=1, max_length=100)
    config_values: dict[str, Any] = Field(default_factory=dict)


class EnabledSkillResponse(BaseModel):
    """Response model for an enabled skill (secrets masked)."""

    skill_id: str
    config_keys: list[str]
    created_at: str
    updated_at: str


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@router.get("/registry", response_model=list[SkillRegistryEntry])
async def list_registry(
    registry: Annotated[SkillsRegistryInterface, Depends(get_registry)],
) -> list[SkillRegistryEntry]:
    """
    List all available skills from the registry.

    Scans the skills directory and returns metadata from each skill's config.json.
    Does not require the skill to be enabled.
    """
    return registry.list_skills()


@router.get("/{skill_id}/schema", response_model=Form)
async def get_skill_schema(
    skill_id: str,
    registry: Annotated[SkillsRegistryInterface, Depends(get_registry)],
) -> Form:
    """
    Get the form schema for a skill.

    Returns the schema used to collect user configuration when enabling the skill.
    Returns 404 if the skill has no schema or does not exist.
    """
    raw_schema = registry.get_schema(skill_id)
    if raw_schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schema found for skill: {skill_id}",
        )

    form = parse_form_schema(raw_schema)
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid schema for skill: {skill_id}",
        )
    return form


@router.post("/enable", status_code=status.HTTP_201_CREATED)
async def enable_skill(
    request: Request,
    body: EnableSkillRequest,
    registry: Annotated[SkillsRegistryInterface, Depends(get_registry)],
    config_repo: Annotated[UserSkillConfigRepository, Depends(get_config_repository)],
) -> dict[str, Any]:
    """
    Enable a skill for the current user with the provided configuration.

    Validates that the skill exists. If the skill has a schema, config_values
    should match the expected form fields. Uses a common endpoint for all skills.
    """
    user_email: str = request.state.user_email

    config = registry.get_config(body.skill_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {body.skill_id}",
        )

    user_config = UserSkillConfig(
        user_email=user_email,
        skill_id=body.skill_id,
        config_values=body.config_values,
        created_at="",
        updated_at="",
    )
    config_repo.save(user_config)

    return {
        "skill_id": body.skill_id,
        "message": "Skill enabled successfully",
    }


@router.get("/enabled", response_model=list[EnabledSkillResponse])
async def list_enabled_skills(
    request: Request,
    config_repo: Annotated[UserSkillConfigRepository, Depends(get_config_repository)],
) -> list[EnabledSkillResponse]:
    """
    List all skills enabled for the current user.

    Returns config keys only (no values) to avoid exposing secrets.
    """
    user_email: str = request.state.user_email
    configs = config_repo.list_enabled(user_email)

    return [
        EnabledSkillResponse(
            skill_id=c.skill_id,
            config_keys=list(c.config_values.keys()),
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in configs
    ]


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_skill(
    request: Request,
    skill_id: str,
    config_repo: Annotated[UserSkillConfigRepository, Depends(get_config_repository)],
) -> None:
    """
    Disable a skill for the current user.

    Removes the stored configuration for this skill.
    """
    user_email: str = request.state.user_email
    config_repo.delete(user_email, skill_id)
