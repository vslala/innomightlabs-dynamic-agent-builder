"""An agent's memory blocks in a blueprint: added, changed and taken away like its skills, in the owner's own memory
with the agent (memory is per person, keyed by email, as on the agent's Memory page)."""

import pytest
import yaml
from fastapi import BackgroundTasks

from src.agents.repository import AgentRepository
from src.blueprints.commands import UNDO_ACTIONS
from src.blueprints.kinds.agent import AgentKind, SaveMemoryBlock
from src.blueprints.kits import KitRepository, declared
from src.blueprints.planner import plan_blueprint
from src.blueprints.service import Deployed, deploy_blueprint
from src.blueprints.validator import validate_blueprint
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.memory.repository import MemoryRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, account_for
from tests.mock_data import test_owner as _test_owner

TEST_OWNER = _test_owner()

PROJECTS = {"name": "projects", "description": "The projects this person is working on."}
GOALS = {"name": "goals", "description": "What this person wants to achieve.", "word_limit": 800}


def blueprint(*blocks: dict) -> str:
    agent: dict = {"kind": "Agent", "name": "Helper", "provider": "Bedrock", "instructions": "Help people."}
    if blocks:
        agent["memory_blocks"] = list(blocks)
    return yaml.safe_dump({
        "apiVersion": "innomight/v2", "kind": "Blueprint", "metadata": {"name": "helper", "title": "Helper"},
        "resources": {"helper": agent},
    }, sort_keys=False)


@pytest.fixture(autouse=True)
def provider(dynamodb_table) -> None:
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )


def deploy(text: str, kit_id: str | None = None) -> Deployed:
    outcome = deploy_blueprint(text, {}, TEST_OWNER, BackgroundTasks(), kit_id=kit_id)
    assert isinstance(outcome, Deployed), outcome
    return outcome


def custom_blocks(agent_id: str, user_id: str = TEST_USER_EMAIL) -> dict[str, tuple[str, int]]:
    return {
        block.block_name: (block.description, block.word_limit)
        for block in MemoryRepository().get_block_definitions(agent_id, user_id)
        if not block.is_default
    }


def remember(agent_id: str, block_name: str, *lines: str) -> None:
    MemoryRepository().save_core_memory(
        CoreMemory(agent_id=agent_id, user_id=TEST_USER_EMAIL, block_name=block_name, lines=list(lines))
    )


def plan_next(text: str, kit_id: str):
    kit = KitRepository().find(TEST_OWNER.account_id, kit_id)
    return plan_blueprint(validate_blueprint(text, {}), TEST_OWNER, declared(kit))


def test_applying_adds_the_blocks_to_the_owners_memory_with_the_agent():
    deployed = deploy(blueprint(PROJECTS, GOALS))
    agent_id = deployed.deployment.resources["helper"].id

    assert custom_blocks(agent_id) == {"projects": (PROJECTS["description"], 5000), "goals": (GOALS["description"], 800)}
    # Memory stays per person: someone else chatting with the agent doesn't get them
    assert custom_blocks(agent_id, TEST_USER_EMAIL_2) == {}


def test_the_blocks_show_on_the_agents_memory_page(test_client, auth_headers):
    agent_id = deploy(blueprint(PROJECTS)).deployment.resources["helper"].id

    listed = test_client.get(f"/agents/{agent_id}/memory-blocks", headers=auth_headers)

    assert listed.status_code == 200, listed.text
    assert [block["block_name"] for block in listed.json()] == ["human", "persona", "projects"]


def test_applying_again_changes_nothing():
    kit = deploy(blueprint(PROJECTS)).kit

    plan = plan_next(blueprint(PROJECTS), kit.kit_id)
    assert plan.ok and [step.action for step in plan.steps] == ["unchanged"]


def test_changing_a_block_keeps_what_it_holds():
    deployed = deploy(blueprint(PROJECTS))
    agent_id = deployed.deployment.resources["helper"].id
    remember(agent_id, "projects", "Launching a shop in May")

    changed = {**PROJECTS, "description": "Projects and their deadlines.", "word_limit": 2000}
    plan = plan_next(blueprint(changed), deployed.kit.kit_id)
    assert "update memory block projects" in plan.steps[0].changes
    deploy(blueprint(changed), deployed.kit.kit_id)

    assert custom_blocks(agent_id) == {"projects": ("Projects and their deadlines.", 2000)}
    assert MemoryRepository().get_core_memory(agent_id, TEST_USER_EMAIL, "projects").lines == ["Launching a shop in May"]


def test_leaving_a_block_out_takes_it_away_with_what_it_holds():
    deployed = deploy(blueprint(PROJECTS, GOALS))
    agent_id = deployed.deployment.resources["helper"].id
    remember(agent_id, "projects", "Launching a shop in May")

    plan = plan_next(blueprint(GOALS), deployed.kit.kit_id)
    assert plan.ok and plan.removals == ["remove memory block projects and what it holds"]
    removed = deploy(blueprint(GOALS), deployed.kit.kit_id)

    assert removed.deployment.removed == ["remove memory block projects and what it holds"]
    assert set(custom_blocks(agent_id)) == {"goals"}
    assert MemoryRepository().get_core_memory(agent_id, TEST_USER_EMAIL, "projects") is None


def test_a_block_the_kit_never_declared_is_left_alone():
    deployed = deploy(blueprint())
    agent_id = deployed.deployment.resources["helper"].id
    MemoryRepository().save_block_definition(MemoryBlockDefinition(
        agent_id=agent_id, user_id=TEST_USER_EMAIL, block_name="added_on_the_page", description="Kept",
    ))

    plan = plan_next(blueprint(), deployed.kit.kit_id)
    assert plan.ok and plan.removals == []


def test_ila_reads_a_block_added_on_the_memory_page_and_not_the_defaults():
    agent_id = deploy(blueprint()).deployment.resources["helper"].id
    MemoryRepository().initialize_default_blocks(agent_id, TEST_USER_EMAIL)
    MemoryRepository().save_block_definition(MemoryBlockDefinition(
        agent_id=agent_id, user_id=TEST_USER_EMAIL, block_name="projects", description="Mine", word_limit=600,
    ))

    observed = AgentKind().observe(AgentRepository().get(agent_id), {})

    assert observed["memory_blocks"] == [{"name": "projects", "description": "Mine", "word_limit": 600}]


@pytest.mark.parametrize("blocks, message", [
    ([{"name": "human", "description": "x"}], "already has"),
    ([PROJECTS, dict(PROJECTS)], "more than once"),
    ([{"name": "Bad Name", "description": "x"}], "pattern"),
])
def test_blocks_a_blueprint_cant_have_are_reported(blocks, message):
    outcome = deploy_blueprint(blueprint(*blocks), {}, TEST_OWNER, BackgroundTasks())
    assert not isinstance(outcome, Deployed)
    assert any(message in issue.message for issue in outcome.issues)


def test_undoing_an_added_block_takes_it_off_and_a_changed_one_puts_it_back():
    agent_id = deploy(blueprint(PROJECTS)).deployment.resources["helper"].id
    undo = UNDO_ACTIONS["restore_memory_block"]

    undo({"agent_id": agent_id, "name": "projects", "block": {**PROJECTS, "word_limit": 700}}, TEST_OWNER)
    assert custom_blocks(agent_id) == {"projects": (PROJECTS["description"], 700)}

    undo({"agent_id": agent_id, "name": "projects", "block": None}, TEST_OWNER)
    assert custom_blocks(agent_id) == {}
    assert SaveMemoryBlock.reversibility.value == "reversible"
