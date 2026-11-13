"""The account's image generation: the setting admins choose, who draws because of it, and the OpenAI API adapter."""

import pytest

from src.llm.images import ImageGenerationOptions
from src.llm.providers import provider
from src.agents.image_generation.service import (
    AgentImageGenerationError,
    AgentImageGenerationService,
    ImageGenerationNotSupportedError,
)
from src.agents.image_generation.settings import ImageGenerationSettings, ImageGenerationSettingsRepository
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.llm.models import ModelInfo
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.llm_doubles import ListedModels, use_provider
from tests.mock_data import TEST_USER_EMAIL, account_for, agent_fields
from tests.test_agent_image_provider import FakeAsyncClient, FakeStreamResponse

ACCOUNT = account_for(TEST_USER_EMAIL)


def provider_set_up(name: str) -> None:
    ProviderSettingsRepository().save(ProviderSettings(account_id=ACCOUNT, provider_name=name, encrypted_credentials="{}"))


@pytest.fixture
def drawing_models(dynamodb_table, monkeypatch):
    """OpenAIAPI lists one model that can draw and one that can't."""
    models = [
        ModelInfo(model_id="gpt-5.5", model_name="gpt-5.5", display_name="GPT-5.5", provider="openai_api",
                  capabilities=["image_generation"]),
        ModelInfo(model_id="embed", model_name="embed", display_name="Embed", provider="openai_api"),
    ]
    use_provider(monkeypatch, "OpenAIAPI", catalog=ListedModels(models))
    provider_set_up("OpenAIAPI")


def agent_on(provider: str, model: str = "claude-haiku") -> Agent:
    return AgentRepository().save(Agent(
        agent_name="Artist", agent_architecture="krishna-memgpt", agent_provider=provider, agent_model=model,
        agent_persona="You draw.", **agent_fields(TEST_USER_EMAIL),
    ))


# --- The setting ------------------------------------------------------------------------------


def test_the_setting_starts_off(test_client, auth_headers, dynamodb_table):
    shown = test_client.get("/image-generation/settings", headers=auth_headers).json()
    assert shown == {"enabled": False, "provider_name": None, "model_name": None, "is_configured": False}


def test_an_admin_turns_it_on_with_a_model_that_can_draw(test_client, auth_headers, drawing_models):
    saved = test_client.put("/image-generation/settings", headers=auth_headers,
                            json={"enabled": True, "provider_name": "OpenAIAPI", "model_name": "gpt-5.5"})

    assert saved.status_code == 200, saved.text
    assert saved.json()["is_configured"] is True
    assert ImageGenerationSettingsRepository().find_in_account(ACCOUNT).model_name == "gpt-5.5"


def test_a_model_that_cant_draw_is_refused(test_client, auth_headers, drawing_models):
    refused = test_client.put("/image-generation/settings", headers=auth_headers,
                              json={"enabled": True, "provider_name": "OpenAIAPI", "model_name": "embed"})

    assert refused.status_code == 400 and "can't draw" in refused.json()["detail"]
    assert ImageGenerationSettingsRepository().find_in_account(ACCOUNT) is None


def test_the_form_offers_only_models_that_can_draw(test_client, auth_headers, drawing_models):
    form = test_client.get("/image-generation/settings/schema", headers=auth_headers).json()

    model_field = next(field for field in form["form_inputs"] if field["name"] == "model_name")
    assert [option["value"] for option in model_field["options"]] == ["gpt-5.5"]


def test_turning_it_off_clears_the_model(test_client, auth_headers, drawing_models):
    test_client.put("/image-generation/settings", headers=auth_headers,
                    json={"enabled": True, "provider_name": "OpenAIAPI", "model_name": "gpt-5.5"})
    test_client.put("/image-generation/settings", headers=auth_headers, json={"enabled": False})

    saved = ImageGenerationSettingsRepository().find_in_account(ACCOUNT)
    assert (saved.enabled, saved.provider_name, saved.model_name) == (False, None, None)


def test_agents_of_an_account_with_it_set_up_offer_image_generation(test_client, auth_headers, drawing_models):
    agent_on("Bedrock")
    capabilities = lambda: test_client.get("/agents", headers=auth_headers).json()[0]["capabilities"]  # noqa: E731
    assert "image_generation" not in capabilities()

    test_client.put("/image-generation/settings", headers=auth_headers,
                    json={"enabled": True, "provider_name": "OpenAIAPI", "model_name": "gpt-5.5"})

    assert "image_generation" in capabilities()


# --- Who draws --------------------------------------------------------------------------------


def test_the_accounts_setting_draws_for_an_agent_that_cant(drawing_models):
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=ACCOUNT, enabled=True, provider_name="OpenAIAPI", model_name="gpt-5.5"))

    artist = AgentImageGenerationService()._artist_for(agent_on("Bedrock"))

    assert (artist.provider_name, artist.model) == ("OpenAIAPI", "gpt-5.5")


def test_without_the_setting_an_agent_whose_own_provider_can_draw_still_does(dynamodb_table):
    provider_set_up("OpenAI")

    artist = AgentImageGenerationService()._artist_for(agent_on("OpenAI", "gpt-5.4"))

    assert (artist.provider_name, artist.model) == ("OpenAI", "gpt-5.4")


def test_an_agent_that_cant_draw_is_told_where_to_set_it_up(dynamodb_table):
    with pytest.raises(ImageGenerationNotSupportedError, match="Settings > Image Generation"):
        AgentImageGenerationService()._artist_for(agent_on("Anthropic"))


def test_the_chosen_provider_must_still_be_set_up(dynamodb_table):
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=ACCOUNT, enabled=True, provider_name="OpenAIAPI", model_name="gpt-5.5"))

    with pytest.raises(AgentImageGenerationError, match="not configured"):
        AgentImageGenerationService()._artist_for(agent_on("Bedrock"))


# --- The OpenAI API adapter -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_openai_api_adapter_draws_with_the_api_key_at_the_public_endpoint(monkeypatch):
    sent: dict = {}

    class RecordingClient(FakeAsyncClient):
        def stream(self, method, url, headers=None, json=None):
            sent.update(url=url, authorization=(headers or {}).get("Authorization"), model=(json or {}).get("model"))
            return FakeStreamResponse()

    monkeypatch.setattr("src.llm.wire.responses_images.httpx.AsyncClient", RecordingClient)

    images = await provider("OpenAIAPI").images.generate(
        prompt="red pixel", credentials={"api_key": "sk-test"}, model="gpt-5.5",
        options=ImageGenerationOptions(output_format="png"),
    )

    assert sent == {"url": "https://api.openai.com/v1/responses", "authorization": "Bearer sk-test", "model": "gpt-5.5"}
    assert len(images) == 1 and images[0].provider_metadata["provider"] == "openai_api"


@pytest.mark.asyncio
async def test_the_openai_api_adapter_wants_an_api_key():
    with pytest.raises(ValueError, match="api_key"):
        await provider("OpenAIAPI").images.generate(
            prompt="x", credentials={}, model="gpt-5.5", options=ImageGenerationOptions())
