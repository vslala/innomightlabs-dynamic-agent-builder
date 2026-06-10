from datetime import datetime, timezone

from src.agents.architectures.krishna_memgpt_prompt import build_krishna_memgpt_system_prompt
from src.agents.models import MemoryCapacityWarning
from src.memory.snapshot import (
    CoreMemoryBlockDefSnapshot,
    CoreMemoryBlockSnapshot,
    CoreMemorySnapshot,
)
from src.skills.models import AgentSkill


def _core_memory_snapshot() -> CoreMemorySnapshot:
    return CoreMemorySnapshot(
        block_defs=[
            CoreMemoryBlockDefSnapshot(
                block_name="human",
                description="Facts about the user",
                word_limit=100,
            ),
            CoreMemoryBlockDefSnapshot(
                block_name="persona",
                description="Agent traits",
                word_limit=100,
            ),
        ],
        blocks={
            "human": CoreMemoryBlockSnapshot(
                block_name="human",
                lines=["User likes concise answers", "User builds automations"],
                word_count=10,
            ),
        },
    )


def test_krishna_memgpt_prompt_renders_required_sections():
    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="You are a careful backend engineer.",
        memory_repo=None,
        agent_id="agent-1",
        user_id="user-1",
        core_memory=_core_memory_snapshot(),
    )

    assert "<identity>" in prompt
    assert "Current date and time:" in prompt
    assert "ANCHOR_TASK: Answer the user's latest request." in prompt
    assert "ANCHOR_PERSONA:" in prompt
    assert "You are a careful backend engineer." in prompt
    assert "<core_memory>" in prompt
    assert "ANCHOR_MEMORY_SNAPSHOT:" in prompt
    assert "BLOCK=human | DESCRIPTION=Facts about the user | CAPACITY=10/100 words" in prompt
    assert "1: User likes concise answers" in prompt
    assert "BLOCK=persona | DESCRIPTION=Agent traits" in prompt
    assert "(empty)" in prompt
    assert "<memory_tools>" in prompt
    assert "ANCHOR_NO_REPEAT_READ:" in prompt


def test_krishna_memgpt_prompt_omits_optional_sections_when_data_absent():
    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="Persona",
        memory_repo=None,
        agent_id="agent-1",
        user_id="user-1",
        core_memory=_core_memory_snapshot(),
        kb_count=0,
        enabled_skills=[],
        capacity_warnings=[],
    )

    assert "<knowledge_base>" not in prompt
    assert "<skills>" not in prompt
    assert "<memory_warning>" not in prompt


def test_krishna_memgpt_prompt_renders_optional_sections_when_data_present():
    skill = AgentSkill(
        agent_id="agent-1",
        skill_id="google_drive",
        namespace="google",
        skill_name="Google Drive",
        skill_description="Search Drive files",
        installed_by="user@example.com",
        installed_at=datetime.now(timezone.utc),
    )
    warning = MemoryCapacityWarning(
        block_name="human",
        word_count=90,
        word_limit=100,
        percent=90.0,
    )

    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="Persona",
        memory_repo=None,
        agent_id="agent-1",
        user_id="user-1",
        core_memory=_core_memory_snapshot(),
        kb_count=2,
        enabled_skills=[skill],
        capacity_warnings=[warning],
    )

    assert "<knowledge_base>" in prompt
    assert "You have access to 2 knowledge base(s)" in prompt
    assert "<skills>" in prompt
    assert "- google_drive: Google Drive - Search Drive files" in prompt
    assert "<memory_warning>" in prompt
    assert "- [human]: 90/100 words (90%)" in prompt
