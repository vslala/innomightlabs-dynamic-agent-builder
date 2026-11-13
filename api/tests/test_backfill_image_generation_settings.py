"""The one-off Image Generation settings: for accounts whose agents drew with their own model, and for saved models
that no longer draw."""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.agents.image_generation.settings import ImageGenerationSettings, ImageGenerationSettingsRepository
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.config import settings
from src.db import get_dynamodb_resource
from src.llm.models import ModelInfo
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.llm_doubles import ListedModels, use_provider
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, account_for, agent_fields

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backfill_image_generation_settings.py"


def load_script():
    spec = importlib.util.spec_from_file_location("backfill_image_generation_settings", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def agent_on(provider: str, model: str, *, email: str = TEST_USER_EMAIL, days_ago: int = 0) -> Agent:
    agent = Agent(
        agent_name=f"{provider} {model}", agent_architecture="krishna-memgpt", agent_provider=provider,
        agent_model=model, agent_persona="Helpful", **agent_fields(email),
    )
    agent.updated_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return AgentRepository().save(agent)


def provider_set_up(name: str, email: str = TEST_USER_EMAIL) -> None:
    ProviderSettingsRepository().save(ProviderSettings(account_id=account_for(email), provider_name=name, encrypted_credentials="{}"))


def planned(script) -> tuple[list[ImageGenerationSettings], dict[str, int]]:
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    to_write, skipped = script.settings_to_write(
        script.agents(table), script.saved_settings(table), ProviderSettingsRepository()
    )
    return to_write, dict(skipped)


def model(name: str, *capabilities: str) -> ModelInfo:
    return ModelInfo(model_id=name, model_name=name, display_name=name, provider="p", capabilities=list(capabilities))


@pytest.fixture(autouse=True)
def catalogs(monkeypatch):
    """ChatGPT's chat models draw (they host the tool); the API key draws only with `gpt-image-2`."""
    use_provider(monkeypatch, "OpenAI", catalog=ListedModels([model("gpt-5.5", "chat", "image_generation")]))
    use_provider(monkeypatch, "OpenAIAPI", catalog=ListedModels([model("gpt-5.5", "chat"), model("gpt-image-2", "image_generation")]))


def test_an_account_drawing_through_its_chatgpt_agent_keeps_that_agents_model(dynamodb_table):
    provider_set_up("OpenAI")
    # Saved newest first, so the choice follows the agents' own times, not the order they were written
    agent_on("OpenAI", "gpt-5.5", days_ago=1)
    agent_on("OpenAI", "gpt-5.4", days_ago=3)
    agent_on("Anthropic", "claude-haiku")

    to_write, skipped = planned(load_script())

    assert [(s.account_id, s.enabled, s.provider_name, s.model_name) for s in to_write] == [
        (account_for(TEST_USER_EMAIL), True, "OpenAI", "gpt-5.5")
    ]
    assert skipped == {}


def test_an_api_key_agents_chat_model_no_longer_draws_so_the_catalogs_image_model_is_chosen(dynamodb_table):
    provider_set_up("OpenAIAPI")
    agent_on("OpenAIAPI", "gpt-5.5")

    to_write, _ = planned(load_script())

    assert [(s.provider_name, s.model_name) for s in to_write] == [("OpenAIAPI", "gpt-image-2")]


def test_a_saved_setting_whose_model_no_longer_draws_is_moved_to_one_that_does(dynamodb_table):
    provider_set_up("OpenAIAPI")
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=account_for(TEST_USER_EMAIL), enabled=True, provider_name="OpenAIAPI", model_name="gpt-5.5"))

    to_write, _ = planned(load_script())

    assert [(s.account_id, s.model_name, s.enabled) for s in to_write] == [(account_for(TEST_USER_EMAIL), "gpt-image-2", True)]


def test_settings_that_draw_and_accounts_without_the_provider_are_left_alone(dynamodb_table):
    provider_set_up("OpenAI")
    agent_on("OpenAI", "gpt-5.5")
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=account_for(TEST_USER_EMAIL), enabled=True, provider_name="OpenAI", model_name="gpt-5.5"))
    agent_on("OpenAIAPI", "gpt-5.5", email=TEST_USER_EMAIL_2)  # its key was removed

    to_write, skipped = planned(load_script())

    assert to_write == []
    assert skipped == {"OpenAIAPI is no longer configured": 1}


def test_an_agent_from_before_accounts_is_skipped_and_counted_not_a_crash(dynamodb_table):
    """Production still holds agents saved before accounts existed: no `account_id`."""
    provider_set_up("OpenAIAPI")
    agent_on("OpenAIAPI", "gpt-5.5")
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    table.put_item(Item={"pk": "Agent#legacy", "sk": "Agent#legacy", "entity_type": "Agent", "agent_id": "legacy"})
    script = load_script()
    old_agents: dict = script.Counter()

    kept = list(script.agents(table, old_agents))

    assert [a.agent_provider for a in kept] == ["OpenAIAPI"]
    assert dict(old_agents) == {"agent from before accounts (no account_id)": 1}


def test_a_dry_run_writes_nothing_and_apply_writes_the_setting(dynamodb_table, monkeypatch, capsys):
    provider_set_up("OpenAIAPI")
    agent_on("OpenAIAPI", "gpt-5.5")
    script = load_script()

    monkeypatch.setattr(sys, "argv", ["backfill"])
    script.main()
    assert ImageGenerationSettingsRepository().find_in_account(account_for(TEST_USER_EMAIL)) is None
    assert "would write" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["backfill", "--apply"])
    script.main()
    saved = ImageGenerationSettingsRepository().find_in_account(account_for(TEST_USER_EMAIL))
    assert saved is not None and saved.is_configured and saved.model_name == "gpt-image-2"
