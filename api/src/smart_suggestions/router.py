"""Router for authenticated dashboard smart suggestions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.form_models import Form
from src.accounts.owner import Owner
from src.form_options import FormOptionsContext, hydrate_form_options, validate_form_options
from src.iam.dependencies import get_owner, get_principal
from src.iam.principal import Principal
from src.settings.access import settings_manager
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
    principal: Annotated[Principal, Depends(get_principal)],
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
) -> SmartSuggestionSettingsResponse:
    """The account's settings; any member may read them."""
    return SmartSuggestionSettingsResponse.from_settings(repository.find_in_account(principal.account_id))


@router.get("/settings/schema", response_model=Form, response_model_exclude_none=True)
async def get_settings_schema(
    owner: Annotated[Owner, Depends(get_owner)],
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
    provider_settings_repository: Annotated[
        ProviderSettingsRepository,
        Depends(get_provider_settings_repository),
    ],
) -> Form:
    form = build_smart_suggestion_settings_form(repository.find_in_account(owner.account_id))
    return hydrate_form_options(
        form,
        FormOptionsContext(
            owner=owner,
            provider_settings_repository=provider_settings_repository,
        ),
    )


@router.put("/settings", response_model=SmartSuggestionSettingsResponse)
async def save_settings(
    request: Request,
    body: SmartSuggestionSettingsRequest,
    principal: Annotated[Principal, Depends(settings_manager)],
    repository: Annotated[
        SmartSuggestionSettingsRepository,
        Depends(get_smart_suggestion_settings_repository),
    ],
    provider_settings_repository: Annotated[
        ProviderSettingsRepository,
        Depends(get_provider_settings_repository),
    ],
) -> SmartSuggestionSettingsResponse:
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
                owner=get_owner(request),
                provider_settings_repository=provider_settings_repository,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    settings = SmartSuggestionSettings(
        account_id=principal.account_id,
        updated_by=principal.user_id,
        enabled=body.enabled,
        provider_name=body.provider_name if body.enabled else None,
        model_name=body.model_name if body.enabled else None,
    )
    saved = repository.save(settings)
    return SmartSuggestionSettingsResponse.from_settings(saved)


@router.post("", response_model=SmartSuggestionResponse)
async def create_suggestion(
    body: SmartSuggestionRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[SmartSuggestionService, Depends(get_smart_suggestion_service)],
) -> SmartSuggestionResponse:
    try:
        return await service.suggest(account_id=principal.account_id, request=body)
    except SmartSuggestionNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SmartSuggestionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

