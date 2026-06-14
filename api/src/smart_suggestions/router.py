"""Router for authenticated dashboard smart suggestions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.form_models import Form
from src.form_options import FormOptionsContext, hydrate_form_options, validate_form_options
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.smart_suggestions.models import (
    SmartSuggestionRequest,
    SmartSuggestionResponse,
    SmartSuggestionSettings,
    SmartSuggestionSettingsRequest,
    SmartSuggestionSettingsResponse,
)
from src.smart_suggestions.repository import (
    SmartSuggestionSettingsRepository,
    get_smart_suggestion_settings_repository,
)
from src.smart_suggestions.schemas import build_smart_suggestion_settings_form
from src.smart_suggestions.service import (
    SmartSuggestionNotConfiguredError,
    SmartSuggestionService,
    get_smart_suggestion_service,
)
from src.smart_suggestions.strategies import SmartSuggestionError

security = HTTPBearer()

router = APIRouter(
    prefix="/smart-suggestions",
    tags=["smart-suggestions"],
    dependencies=[Depends(security)],
)


@router.get("/settings", response_model=SmartSuggestionSettingsResponse)
async def get_settings(
    request: Request,
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
) -> SmartSuggestionSettingsResponse:
    user_email: str = request.state.user_email
    return SmartSuggestionSettingsResponse.from_settings(repository.find_by_user(user_email))


@router.get("/settings/schema", response_model=Form, response_model_exclude_none=True)
async def get_settings_schema(
    request: Request,
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
    provider_settings_repository: Annotated[
        ProviderSettingsRepository,
        Depends(get_provider_settings_repository),
    ],
) -> Form:
    user_email: str = request.state.user_email
    form = build_smart_suggestion_settings_form(repository.find_by_user(user_email))
    return hydrate_form_options(
        form,
        FormOptionsContext(
            user_email=user_email,
            provider_settings_repository=provider_settings_repository,
        ),
    )


@router.put("/settings", response_model=SmartSuggestionSettingsResponse)
async def save_settings(
    request: Request,
    body: SmartSuggestionSettingsRequest,
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
    provider_settings_repository: Annotated[
        ProviderSettingsRepository,
        Depends(get_provider_settings_repository),
    ],
) -> SmartSuggestionSettingsResponse:
    user_email: str = request.state.user_email
    form = build_smart_suggestion_settings_form()
    values = {
        "enabled": "true" if body.enabled else "false",
        "provider_name": body.provider_name or "",
        "model_name": body.model_name or "",
    }
    try:
        validate_form_options(
            form.form_inputs,
            values,
            FormOptionsContext(
                user_email=user_email,
                provider_settings_repository=provider_settings_repository,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    settings = SmartSuggestionSettings(
        user_email=user_email,
        enabled=body.enabled,
        provider_name=body.provider_name if body.enabled else None,
        model_name=body.model_name if body.enabled else None,
    )
    saved = repository.save(settings)
    return SmartSuggestionSettingsResponse.from_settings(saved)


@router.post("", response_model=SmartSuggestionResponse)
async def create_suggestion(
    request: Request,
    body: SmartSuggestionRequest,
    service: Annotated[SmartSuggestionService, Depends(get_smart_suggestion_service)],
) -> SmartSuggestionResponse:
    user_email: str = request.state.user_email
    try:
        return await service.suggest(user_email=user_email, request=body)
    except SmartSuggestionNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SmartSuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

