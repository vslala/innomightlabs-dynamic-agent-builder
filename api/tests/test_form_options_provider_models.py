"""Models filtered by the chosen provider: option groups, the filter rule, and pair validation."""

import httpx
import pytest
from fastapi.testclient import TestClient

from src.agents.schemas import get_create_agent_form
from src.dream.schemas import build_dream_settings_form
from src.form_models import FormOptionsFilter, SelectOption
from src.smart_suggestions.schemas import build_smart_suggestion_settings_form
from tests.mock_data import AGENT_CREATE_REQUEST

#: Bedrock's list call isn't in moto, so its fallback models are what the forms offer.
BEDROCK_MODEL = "claude-3-sonnet"
OPENAI_API_PAYLOAD = {"data": [{"id": "gpt-5.5", "created": 2}, {"id": "gpt-4.1", "created": 1}]}


class TestFilterRule:
    OPTIONS = [
        SelectOption(value="claude-3-sonnet", label="Claude", group="Bedrock"),
        SelectOption(value="gpt-5.5", label="GPT via OAuth", group="OpenAI"),
        SelectOption(value="gpt-5.5", label="GPT via API key", group="OpenAIAPI"),
        SelectOption(value="default", label="Provider default"),
    ]

    def test_offers_only_the_selected_groups_options_and_ungrouped_ones(self):
        options = FormOptionsFilter(field="agent_provider").apply(self.OPTIONS, {"agent_provider": "OpenAIAPI"})

        assert [(option.label, option.group) for option in options] == [
            ("GPT via API key", "OpenAIAPI"),
            ("Provider default", None),
        ]

    def test_nothing_selected_offers_only_ungrouped_options(self):
        options = FormOptionsFilter(field="agent_provider").apply(self.OPTIONS, {})

        assert [option.value for option in options] == ["default"]


@pytest.mark.parametrize(
    ("form", "provider_field", "model_field"),
    [
        (get_create_agent_form(), "agent_provider", "agent_model"),
        (build_smart_suggestion_settings_form(None), "provider_name", "model_name"),
        (build_dream_settings_form(None), "provider_name", "model_name"),
    ],
)
def test_every_model_field_filters_by_its_forms_provider_field(form, provider_field, model_field):
    fields = {field.name: field for field in form.form_inputs}

    assert fields[model_field].options_filter == FormOptionsFilter(field=provider_field)


@pytest.fixture
def openai_api_configured(test_client: TestClient, auth_headers: dict, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        request = httpx.Request("GET", url, headers=headers)
        return httpx.Response(200, json=OPENAI_API_PAYLOAD, request=request)

    monkeypatch.setattr("src.llm.models.httpx.get", fake_get)
    response = test_client.post("/settings/providers/OpenAIAPI", json={"api_key": "sk-test"}, headers=auth_headers)
    assert response.status_code == 201


class TestAgentForm:
    def test_model_options_carry_their_provider(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured
    ):
        form = test_client.get("/agents/supported-models", headers=auth_headers).json()

        model_field = next(field for field in form["form_inputs"] if field["name"] == "agent_model")
        groups = {(option["value"], option["group"]) for option in model_field["options"]}
        assert {("gpt-5.5", "OpenAIAPI"), ("gpt-4.1", "OpenAIAPI"), (BEDROCK_MODEL, "Bedrock")} <= groups
        assert model_field["options_filter"] == {"field": "agent_provider"}


class TestAgentPairValidation:
    def _create(self, test_client, auth_headers, provider, model):
        return test_client.post(
            "/agents",
            json={**AGENT_CREATE_REQUEST, "agent_provider": provider, "agent_model": model},
            headers=auth_headers,
        )

    def test_creates_an_agent_with_a_model_of_its_provider(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured
    ):
        assert self._create(test_client, auth_headers, "OpenAIAPI", "gpt-5.5").status_code == 201

    def test_rejects_a_model_from_another_provider(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured
    ):
        response = self._create(test_client, auth_headers, "OpenAIAPI", BEDROCK_MODEL)

        assert response.status_code == 400
        assert response.json()["detail"].startswith(f"{BEDROCK_MODEL} on OpenAIAPI isn't available.")

    def test_rejects_a_provider_that_is_not_set_up(self, test_client: TestClient, auth_headers: dict):
        assert self._create(test_client, auth_headers, "Gemini", "gemini-2.5-flash").status_code == 400

    def test_switching_provider_without_a_matching_model_is_rejected(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured
    ):
        agent_id = self._create(test_client, auth_headers, "Bedrock", BEDROCK_MODEL).json()["agent_id"]

        response = test_client.put(f"/agents/{agent_id}", json={"agent_provider": "OpenAIAPI"}, headers=auth_headers)

        assert response.status_code == 400

    def test_switching_provider_and_model_together_is_saved(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured
    ):
        agent_id = self._create(test_client, auth_headers, "Bedrock", BEDROCK_MODEL).json()["agent_id"]

        response = test_client.put(
            f"/agents/{agent_id}",
            json={"agent_provider": "OpenAIAPI", "agent_model": "gpt-4.1"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert (response.json()["agent_provider"], response.json()["agent_model"]) == ("OpenAIAPI", "gpt-4.1")

    def test_an_unchanged_pair_is_not_rechecked(
        self, test_client: TestClient, auth_headers: dict, openai_api_configured, monkeypatch
    ):
        """An agent whose model its provider has since stopped listing can still have other fields edited."""
        agent_id = self._create(test_client, auth_headers, "OpenAIAPI", "gpt-4.1").json()["agent_id"]
        monkeypatch.setitem(OPENAI_API_PAYLOAD, "data", [{"id": "gpt-5.5", "created": 2}])

        response = test_client.put(
            f"/agents/{agent_id}",
            json={"agent_provider": "OpenAIAPI", "agent_model": "gpt-4.1", "agent_persona": "Be brief."},
            headers=auth_headers,
        )

        assert response.status_code == 200
