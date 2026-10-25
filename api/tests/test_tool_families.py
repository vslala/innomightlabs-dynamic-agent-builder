"""Tool families: which tools a turn offers, and the prompt sections that come with them."""

from datetime import datetime, timezone

from src.agents.architectures.krishna_memgpt_families import TOOL_FAMILIES
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.families import ToolFamily, active_families, prompt_sections
from src.agents.tool_runtime.specs import ToolCategory
from src.messages.models import MessageReference
from src.skills.models import ActorKind, AgentSkill


def _state(**changes) -> AgentTurnState:
    state = AgentTurnState(
        owner_email="o@example.com", actor_email="a@example.com", actor_id="a", actor_kind=ActorKind.OWNER,
        conversation_id="c", agent_id="agent", model_name="m", user_message="hi",
    )
    for name, value in changes.items():
        setattr(state, name, value)
    return state


def _categories(state: AgentTurnState) -> set[ToolCategory]:
    return {family.category for family in active_families(TOOL_FAMILIES, state)}


def test_a_bare_agent_is_offered_only_the_native_tools():
    assert _categories(_state()) == {ToolCategory.NATIVE}
    assert prompt_sections(TOOL_FAMILIES, _state()) == []


def test_each_condition_turns_its_family_on_with_its_section():
    skill = AgentSkill(skill_id="google_drive", agent_id="agent", namespace="g", skill_name="Drive", skill_description="Files",
                       installed_by="u", installed_at=datetime.now(timezone.utc))
    connection = type("Connection", (), {"mcp_id": "m", "name": "Jira"})()
    state = _state(linked_kb_ids=["kb-1"], enabled_skills=[skill], enabled_mcp_connections=[connection],
                   image_input_available=True)

    assert _categories(state) >= {ToolCategory.KNOWLEDGE, ToolCategory.SKILL, ToolCategory.MCP, ToolCategory.IMAGE}
    sections = prompt_sections(TOOL_FAMILIES, state)
    assert [section.split("\n", 1)[0] for section in sections][:3] == ["<knowledge_base>", "<skills>", "<mcp_connectors>"]


def test_a_reference_of_its_kind_anywhere_in_the_conversation_turns_a_family_on():
    family = ToolFamily(ToolCategory.DOCUMENT, triggered_by=frozenset({"document"}))

    assert not family.active(_state())
    assert not family.active(_state(references={"other": [MessageReference(kind="other", id="1")]}))
    assert family.active(_state(references={"document": [MessageReference(kind="document", id="d-1")]}))


def test_a_family_with_no_trigger_and_no_condition_is_never_offered():
    assert not ToolFamily(ToolCategory.DOCUMENT).active(_state(linked_kb_ids=["kb"]))
