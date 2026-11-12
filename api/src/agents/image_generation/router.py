"""The account's image generation: who may turn it on and which provider and model draw."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.accounts.owner import Owner
from src.agents.image_generation.settings import (
    ImageGenerationSettings,
    ImageGenerationSettingsRepository,
    ImageGenerationSettingsRequest,
    ImageGenerationSettingsResponse,
    get_image_generation_settings_repository,
)
from src.form_models import Form, FormInput, FormInputType, FormOptionsFilter, FormOptionsSource, SelectOption
from src.form_options import (
    FormOptionSourceType,
    FormOptionsContext,
    ImageGenerationModelsOptionsResolver,
    hydrate_form_options,
)
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.settings.access import settings_manager
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

router = APIRouter(prefix="/image-generation", tags=["image-generation"], dependencies=[Depends(HTTPBearer())])


def build_settings_form(saved: ImageGenerationSettings | None = None) -> Form:
    return Form(
        form_name="Image Generation Settings",
        submit_path="/image-generation/settings",
        form_inputs=[
            FormInput(
                input_type=FormInputType.SELECT,
                name="enabled",
                label="Image generation",
                value="true" if saved and saved.enabled else "false",
                options=[SelectOption(value="true", label="Enabled"), SelectOption(value="false", label="Disabled")],
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="provider_name",
                label="Provider",
                value=saved.provider_name if saved else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS),
            ),
            FormInput(
                input_type=FormInputType.SEARCH,
                name="model_name",
                label="Image model",
                value=saved.model_name if saved else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.IMAGE_GENERATION_MODELS),
                options_filter=FormOptionsFilter(field="provider_name"),
            ),
        ],
    )


@router.get("/settings", response_model=ImageGenerationSettingsResponse)
async def get_settings(
    principal: Annotated[Principal, Depends(get_principal)],
    repository: Annotated[ImageGenerationSettingsRepository, Depends(get_image_generation_settings_repository)],
) -> ImageGenerationSettingsResponse:
    """The account's settings; any member may read them."""
    return ImageGenerationSettingsResponse.from_settings(repository.find_in_account(principal.account_id))


@router.get("/settings/schema", response_model=Form, response_model_exclude_none=True)
async def get_settings_schema(
    owner: Annotated[Owner, Depends(get_owner)],
    repository: Annotated[ImageGenerationSettingsRepository, Depends(get_image_generation_settings_repository)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> Form:
    form = build_settings_form(repository.find_in_account(owner.account_id))
    return hydrate_form_options(
        form, FormOptionsContext(owner=owner, provider_settings_repository=provider_settings_repository)
    )


@router.put("/settings", response_model=ImageGenerationSettingsResponse)
async def save_settings(
    request: Request,
    body: ImageGenerationSettingsRequest,
    principal: Annotated[Principal, Depends(settings_manager)],
    repository: Annotated[ImageGenerationSettingsRepository, Depends(get_image_generation_settings_repository)],
    provider_settings_repository: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> ImageGenerationSettingsResponse:
    """Admins only. An enabled setting must name a model of a connected provider that can draw."""
    if body.enabled:
        context = FormOptionsContext(owner=get_owner(request), provider_settings_repository=provider_settings_repository)
        drawing = ImageGenerationModelsOptionsResolver().resolve(context)
        if not any(model.value == body.model_name and model.group == body.provider_name for model in drawing):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That model can't draw images, or its provider isn't connected. Choose one from the list.",
            )

    saved = repository.save(
        ImageGenerationSettings(
            account_id=principal.account_id,
            updated_by=principal.user_id,
            enabled=body.enabled,
            provider_name=body.provider_name if body.enabled else None,
            model_name=body.model_name if body.enabled else None,
        )
    )
    return ImageGenerationSettingsResponse.from_settings(saved)
