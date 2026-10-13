"""The account's image reading: who may turn it on and which vision model reads images."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer

from src.accounts.owner import Owner
from src.form_models import Form
from src.form_options import FormOptionsContext, VisionModelsOptionsResolver, hydrate_form_options
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.settings.access import settings_manager
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.vision.errors import ImageInputError
from src.vision.models import VisionSettings, VisionSettingsRequest, VisionSettingsResponse
from src.vision.repository import VisionSettingsRepository, get_vision_settings_repository
from src.vision.schemas import build_vision_settings_form

router = APIRouter(prefix="/vision", tags=["vision"], dependencies=[Depends(HTTPBearer())])


@router.get("/settings", response_model=VisionSettingsResponse)
async def get_settings(
    principal: Annotated[Principal, Depends(get_principal)],
    repository: Annotated[VisionSettingsRepository, Depends(get_vision_settings_repository)],
) -> VisionSettingsResponse:
    """The account's settings; any member may read them."""
    return VisionSettingsResponse.from_settings(repository.find_in_account(principal.account_id))


@router.get("/settings/schema", response_model=Form, response_model_exclude_none=True)
async def get_settings_schema(
    owner: Annotated[Owner, Depends(get_owner)],
    repository: Annotated[VisionSettingsRepository, Depends(get_vision_settings_repository)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> Form:
    form = build_vision_settings_form(repository.find_in_account(owner.account_id))
    return hydrate_form_options(
        form, FormOptionsContext(owner=owner, provider_settings_repository=provider_settings_repository)
    )


@router.put("/settings", response_model=VisionSettingsResponse)
async def save_settings(
    request: Request,
    body: VisionSettingsRequest,
    principal: Annotated[Principal, Depends(settings_manager)],
    repository: Annotated[VisionSettingsRepository, Depends(get_vision_settings_repository)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> VisionSettingsResponse:
    """Admins only. An enabled setting must name a model that the provider's own catalog says can read images."""
    if body.enabled:
        _require_vision_model(request, body, provider_settings_repository)

    saved = repository.save(
        VisionSettings(
            account_id=principal.account_id,
            updated_by=principal.user_id,
            enabled=body.enabled,
            provider_name=body.provider_name if body.enabled else None,
            model_name=body.model_name if body.enabled else None,
        )
    )
    return VisionSettingsResponse.from_settings(saved)


def _require_vision_model(
    request: Request, body: VisionSettingsRequest, provider_settings_repository: ProviderSettingsRepository
) -> None:
    context = FormOptionsContext(owner=get_owner(request), provider_settings_repository=provider_settings_repository)
    reads_images = VisionModelsOptionsResolver().resolve(context)
    if not any(model.value == body.model_name and model.group == body.provider_name for model in reads_images):
        raise ImageInputError(
            "vision_model_unsupported",
            "That model can't read images, or its provider isn't connected. Choose one from the list.",
        )
