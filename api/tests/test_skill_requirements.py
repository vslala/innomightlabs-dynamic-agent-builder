"""A skill names what it needs set up in the account (`requires` in its manifest); it can't be installed, and the
catalog shows it unavailable, until the account has it."""

import pytest
import yaml

from src.agents.image_generation.settings import ImageGenerationSettings, ImageGenerationSettingsRepository
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.requirements import SKILL_REQUIREMENTS, requirement_named
from src.skills.service import SkillService
from tests.mock_data import TEST_USER_EMAIL, account_for, agent_fields
from tests.mock_data import test_owner as _test_owner

TEST_OWNER = _test_owner()


@pytest.fixture
def agent(dynamodb_table) -> Agent:
    return AgentRepository().save(Agent(
        agent_name="Artist", agent_architecture="krishna-memgpt", agent_provider="Bedrock",
        agent_model="claude-haiku", agent_persona="You draw.", **agent_fields(TEST_USER_EMAIL),
    ))


def set_up_image_generation() -> None:
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(
        account_id=account_for(TEST_USER_EMAIL), enabled=True, provider_name="OpenAIAPI", model_name="gpt-5.5",
    ))


def install(agent: Agent):
    return SkillService().install_skill(
        agent_id=agent.agent_id, skill_id="image_generation", owner=TEST_OWNER, raw_config={},
    )


def test_a_skill_cant_be_installed_until_the_account_has_what_it_requires(agent):
    with pytest.raises(ValueError, match=r"Image Generation needs image generation set up first.*Settings > Image Generation"):
        install(agent)

    set_up_image_generation()
    assert install(agent).skill_id == "image_generation"


def test_a_requirement_that_is_switched_off_again_is_unmet(agent):
    set_up_image_generation()
    ImageGenerationSettingsRepository().save(ImageGenerationSettings(account_id=account_for(TEST_USER_EMAIL)))

    with pytest.raises(ValueError, match="needs image generation"):
        install(agent)


def test_the_catalog_says_what_is_missing_and_where_to_set_it_up(dynamodb_table):
    account_id = account_for(TEST_USER_EMAIL)

    [item] = [item for item in SkillService().list_catalog(account_id) if item.skill_id == "image_generation"]
    assert item.available is False
    [missing] = item.requirements
    assert (missing.name, missing.met, missing.setup_path) == ("image_generation", False, "/dashboard/settings")

    set_up_image_generation()
    [item] = [item for item in SkillService().list_catalog(account_id) if item.skill_id == "image_generation"]
    assert item.available is True and item.requirements[0].met is True


def test_a_skill_with_no_requirements_is_unaffected(dynamodb_table):
    [item] = [item for item in SkillService().list_catalog(account_for(TEST_USER_EMAIL)) if item.skill_id == "scheduler"]
    assert item.requirements == []


def test_a_manifest_naming_a_requirement_the_platform_doesnt_know_isnt_loaded(tmp_path):
    for skill_id, requires in (("fine", ["image_generation"]), ("typo", ["image_generaton"])):
        folder = tmp_path / skill_id
        folder.mkdir()
        (folder / "manifest.yml").write_text(yaml.safe_dump({
            "id": skill_id, "namespace": "test", "name": skill_id, "description": "x", "requires": requires,
        }))

    assert [loaded.manifest.id for loaded in SkillRegistry(tmp_path).list()] == ["fine"]


def test_every_shipped_manifest_names_known_requirements():
    for loaded in get_skill_registry().list():
        assert all(requirement_named(name) for name in loaded.manifest.requires), loaded.manifest.id
    assert {requirement.name for requirement in SKILL_REQUIREMENTS} >= {"image_generation"}
