"""Skills API router.

Provides:
- Upload skill zip
- List skills
- Activate / deactivate skills

All skills are tenant-scoped (Tenant#owner_email).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.security import HTTPBearer

from src import form_models
from src.skills.models import SkillDefinition, SkillDefinitionResponse, SkillStatus
from src.skills.repository import SkillsRepository
from src.skills.store import SkillsStore, get_skills_store

log = logging.getLogger(__name__)

security = HTTPBearer()

router = APIRouter(prefix="/skills", tags=["skills"], dependencies=[Depends(security)])


@router.get("/forms/upload", response_model=form_models.Form, response_model_exclude_none=True)
async def get_upload_skill_form_schema() -> form_models.Form:
    """Get schema form for skill zip upload."""
    from src.skills.schemas import get_skill_upload_form

    return get_skill_upload_form()


@router.get("/forms/manifest", response_model=form_models.Form, response_model_exclude_none=True)
async def get_manifest_skill_form_schema() -> form_models.Form:
    """Get schema form for creating a skill from manifest JSON."""
    from src.skills.schemas import get_skill_manifest_form

    return get_skill_manifest_form()


def get_skills_repo() -> SkillsRepository:
    return SkillsRepository()


def get_store() -> SkillsStore:
    return get_skills_store()


@router.post("/manifest", response_model=SkillDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_skill_from_manifest(
    request: Request,
    body: dict,
    repo: Annotated[SkillsRepository, Depends(get_skills_repo)] = None,  # type: ignore
    store: Annotated[SkillsStore, Depends(get_store)] = None,  # type: ignore
) -> SkillDefinitionResponse:
    """Create a skill from manifest JSON text (no zip upload required)."""
    owner_email: str = request.state.user_email

    manifest_json = str(body.get("manifest_json", "") or "").strip()
    skill_md = str(body.get("skill_md", "") or "").strip()

    if not manifest_json:
        raise HTTPException(status_code=400, detail="manifest_json is required")

    try:
        from src.skills.models import SkillManifest

        manifest = SkillManifest.model_validate_json(manifest_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid manifest_json: {e}")

    try:
        artifact = store.upload_skill_manifest(owner_email=owner_email, manifest=manifest, skill_md=skill_md)
    except Exception as e:
        log.error(f"Failed to store manifest-based skill: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    skill_def = SkillDefinition(
        owner_email=owner_email,
        skill_id=artifact.manifest.skill_id,
        version=artifact.manifest.version,
        name=artifact.manifest.name,
        description=artifact.manifest.description,
        status=SkillStatus.INACTIVE,
        s3_zip_key=artifact.zip_key,
        s3_manifest_key=artifact.manifest_key,
        s3_skill_md_key=artifact.skill_md_key,
    )

    repo.upsert(skill_def)

    return SkillDefinitionResponse(
        skill_id=skill_def.skill_id,
        version=skill_def.version,
        name=skill_def.name,
        description=skill_def.description,
        status=skill_def.status,
        created_at=skill_def.created_at,
        updated_at=skill_def.updated_at,
    )


@router.get("", response_model=list[SkillDefinitionResponse])
async def list_skills(
    request: Request,
    repo: Annotated[SkillsRepository, Depends(get_skills_repo)],
) -> list[SkillDefinitionResponse]:
    owner_email: str = request.state.user_email
    skills = repo.list_by_owner(owner_email)
    return [
        SkillDefinitionResponse(
            skill_id=s.skill_id,
            version=s.version,
            name=s.name,
            description=s.description,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in skills
    ]


@router.post("/upload", response_model=SkillDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    request: Request,
    file: UploadFile = File(..., description="Skill zip containing manifest.json and SKILL.md"),
    repo: Annotated[SkillsRepository, Depends(get_skills_repo)] = None,  # type: ignore
    store: Annotated[SkillsStore, Depends(get_store)] = None,  # type: ignore
) -> SkillDefinitionResponse:
    owner_email: str = request.state.user_email

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")

    zip_bytes = await file.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        artifact = store.upload_skill_zip(owner_email=owner_email, zip_bytes=zip_bytes)
    except Exception as e:
        log.error(f"Failed to upload skill zip: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    skill_def = SkillDefinition(
        owner_email=owner_email,
        skill_id=artifact.manifest.skill_id,
        version=artifact.manifest.version,
        name=artifact.manifest.name,
        description=artifact.manifest.description,
        status=SkillStatus.INACTIVE,
        s3_zip_key=artifact.zip_key,
        s3_manifest_key=artifact.manifest_key,
        s3_skill_md_key=artifact.skill_md_key,
    )

    repo.upsert(skill_def)

    return SkillDefinitionResponse(
        skill_id=skill_def.skill_id,
        version=skill_def.version,
        name=skill_def.name,
        description=skill_def.description,
        status=skill_def.status,
        created_at=skill_def.created_at,
        updated_at=skill_def.updated_at,
    )


@router.post("/{skill_id}/{version}/activate", response_model=SkillDefinitionResponse)
async def activate_skill(
    request: Request,
    skill_id: str,
    version: str,
    repo: Annotated[SkillsRepository, Depends(get_skills_repo)],
) -> SkillDefinitionResponse:
    owner_email: str = request.state.user_email
    try:
        s = repo.set_status(owner_email, skill_id, version, SkillStatus.ACTIVE)
    except ValueError:
        raise HTTPException(status_code=404, detail="Skill not found")

    return SkillDefinitionResponse(
        skill_id=s.skill_id,
        version=s.version,
        name=s.name,
        description=s.description,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.post("/{skill_id}/{version}/deactivate", response_model=SkillDefinitionResponse)
async def deactivate_skill(
    request: Request,
    skill_id: str,
    version: str,
    repo: Annotated[SkillsRepository, Depends(get_skills_repo)],
) -> SkillDefinitionResponse:
    owner_email: str = request.state.user_email
    try:
        s = repo.set_status(owner_email, skill_id, version, SkillStatus.INACTIVE)
    except ValueError:
        raise HTTPException(status_code=404, detail="Skill not found")

    return SkillDefinitionResponse(
        skill_id=s.skill_id,
        version=s.version,
        name=s.name,
        description=s.description,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )
