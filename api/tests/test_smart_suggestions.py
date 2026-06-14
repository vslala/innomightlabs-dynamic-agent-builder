from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.automations.triggers.schemas import build_schedule_trigger_form
from src.smart_suggestions.models import SmartSuggestionRequest, SmartSuggestionResponse
from src.smart_suggestions.repository import SmartSuggestionSettingsRepository
from src.smart_suggestions.router import get_smart_suggestion_service
from src.smart_suggestions.service import SmartSuggestionService
from src.smart_suggestions.strategies import CronExpressionSuggestionStrategy, SmartSuggestionError
from tests.mock_data import TEST_USER_EMAIL


def test_schedule_trigger_cron_field_declares_smart_suggestion():
    form = build_schedule_trigger_form(nodes=[])

    cron_field = next(field for field in form.form_inputs if field.name == "cron_expression")

    assert cron_field.smart_suggestion is not None
    assert cron_field.smart_suggestion.suggestion_type == "cron_expression"
    assert cron_field.smart_suggestion.prompt_placeholder == "Every weekday at 9 AM"


def test_cron_strategy_parses_and_validates_model_json():
    strategy = CronExpressionSuggestionStrategy()
    request = SmartSuggestionRequest(
        suggestion_type="cron_expression",
        query="Every weekday at 9",
        context={"timezone": "Europe/London"},
    )

    response = strategy.parse_response(
        '{"cron_expression":"0 9 * * 1-5","explanation":"Runs every weekday at 9 AM."}',
        request,
    )

    assert response.value == "0 9 * * 1-5"
    assert response.metadata == {"timezone": "Europe/London"}


def test_cron_strategy_rejects_invalid_cron():
    strategy = CronExpressionSuggestionStrategy()
    request = SmartSuggestionRequest(
        suggestion_type="cron_expression",
        query="Every weekday at 9",
        context={"timezone": "UTC"},
    )

    with pytest.raises(SmartSuggestionError):
        strategy.parse_response(
            '{"cron_expression":"0 9 * *","explanation":"Invalid shape."}',
            request,
        )


def test_smart_suggestion_settings_round_trip(
    test_client: TestClient,
    auth_headers: dict,
):
    response = test_client.put(
        "/smart-suggestions/settings",
        json={
            "enabled": True,
            "provider_name": "Bedrock",
            "model_name": "claude-3-7-sonnet",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_configured"] is True

    repository = SmartSuggestionSettingsRepository()
    saved = repository.find_by_user(TEST_USER_EMAIL)
    assert saved is not None
    assert saved.enabled is True
    assert saved.provider_name == "Bedrock"
    assert saved.model_name == "claude-3-7-sonnet"


def test_smart_suggestion_schema_uses_model_option_sources(
    test_client: TestClient,
    auth_headers: dict,
):
    response = test_client.get("/smart-suggestions/settings/schema", headers=auth_headers)

    assert response.status_code == 200
    fields = response.json()["form_inputs"]
    provider_field = next(field for field in fields if field["name"] == "provider_name")
    model_field = next(field for field in fields if field["name"] == "model_name")

    assert provider_field["options_source"]["type"] == "agent_model_providers"
    assert model_field["options_source"]["type"] == "agent_models"
    assert provider_field["options"]
    assert model_field["options"]


def test_smart_suggestion_endpoint_delegates_to_service(
    test_client: TestClient,
    auth_headers: dict,
):
    class FakeSmartSuggestionService:
        async def suggest(self, *, user_email: str, request: SmartSuggestionRequest) -> SmartSuggestionResponse:
            assert user_email == TEST_USER_EMAIL
            assert request.suggestion_type == "cron_expression"
            assert request.context["timezone"] == "UTC"
            return SmartSuggestionResponse(
                suggestion_type="cron_expression",
                value="0 9 * * 1-5",
                display_text="Runs every weekday at 9 AM.",
                metadata={"timezone": "UTC"},
            )

    from main import app

    app.dependency_overrides[get_smart_suggestion_service] = lambda: FakeSmartSuggestionService()
    try:
        response = test_client.post(
            "/smart-suggestions",
            json={
                "suggestion_type": "cron_expression",
                "query": "Every weekday at 9",
                "context": {"timezone": "UTC"},
            },
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_smart_suggestion_service, None)

    assert response.status_code == 200
    assert response.json()["value"] == "0 9 * * 1-5"

