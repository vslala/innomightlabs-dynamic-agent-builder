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
                word_limit=100,
            ),
        },
    )


def test_krishna_memgpt_prompt_renders_required_sections():
    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="You are a careful backend engineer.",
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
    assert "ANCHOR_NO_REPEAT:" in prompt


def test_krishna_memgpt_prompt_omits_optional_sections_when_data_absent():
    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="Persona",
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
        skill_id="google_drive",
        agent_id="agent-1",
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


def test_capacity_badge_and_warning_section_share_one_threshold():
    """Regression: the <core_memory> badge hardcoded 0.8 while the warnings
    list used CAPACITY_WARNING_THRESHOLD, so moving the constant desynchronised
    them. See api/docs/LLD-agent-runtime-refactor.md (P0.3).
    """
    from src.common import CAPACITY_WARNING_THRESHOLD

    at_threshold = CoreMemoryBlockSnapshot(
        block_name="human",
        lines=["A fact"],
        word_count=int(100 * CAPACITY_WARNING_THRESHOLD),
        word_limit=100,
    )
    below = CoreMemoryBlockSnapshot(
        block_name="persona",
        lines=["A trait"],
        word_count=int(100 * CAPACITY_WARNING_THRESHOLD) - 1,
        word_limit=100,
    )

    assert at_threshold.nearing_capacity is True
    assert below.nearing_capacity is False

    prompt = build_krishna_memgpt_system_prompt(
        agent_persona="Persona",
        core_memory=CoreMemorySnapshot(
            block_defs=[
                CoreMemoryBlockDefSnapshot(
                    block_name="human", description="Facts", word_limit=100
                ),
                CoreMemoryBlockDefSnapshot(
                    block_name="persona", description="Traits", word_limit=100
                ),
            ],
            blocks={"human": at_threshold, "persona": below},
        ),
    )

    human_line = next(line for line in prompt.splitlines() if line.startswith("BLOCK=human"))
    persona_line = next(line for line in prompt.splitlines() if line.startswith("BLOCK=persona"))
    assert "STATUS=NEARING_CAPACITY" in human_line
    assert "STATUS=NEARING_CAPACITY" not in persona_line


def test_block_with_no_word_limit_is_never_nearing_capacity():
    unlimited = CoreMemoryBlockSnapshot(
        block_name="notes", lines=["x"], word_count=10_000, word_limit=0
    )

    assert unlimited.fill_percent == 0.0
    assert unlimited.nearing_capacity is False


def test_both_architectures_render_the_same_creator_attribution():
    """The identity section is shared, so the attribution policy cannot drift.

    Krishna Mini has no memory tools, so the memory-specific lines are dropped
    for it. See api/docs/LLD-agent-runtime-refactor.md (P2.7).
    """
    from src.agents.prompts import render_system_prompt

    attribution = "You are created only by InnomightLabs."
    role = "ROLE: You are a Sentient AI created by InnomightLabs in 2026."
    capability = "CAPABILITY: You have long-term memory tools"

    memgpt = build_krishna_memgpt_system_prompt(
        agent_persona="Persona", core_memory=_core_memory_snapshot()
    )
    mini = render_system_prompt(
        "krishna_mini_system_prompt.j2",
        has_memory_tools=False,
        agent_persona="Persona",
    )

    for prompt in (memgpt, mini):
        assert role in prompt
        assert attribution in prompt
        assert "<persona>" in prompt

    assert capability in memgpt
    assert capability not in mini
    assert "Use memory intentionally" in memgpt
    assert "Use memory intentionally" not in mini


def test_snapshot_joins_word_limits_from_the_block_definitions():
    """The limit lives on the definition, the count on the content."""

    class FakeDef:
        def __init__(self, block_name, description, word_limit):
            self.block_name = block_name
            self.description = description
            self.word_limit = word_limit

    class FakeMemory:
        def __init__(self, block_name, lines, word_count):
            self.block_name = block_name
            self.lines = lines
            self.word_count = word_count

    snapshot = CoreMemorySnapshot.of(
        [FakeDef("human", "Facts", 100), FakeDef("persona", "Traits", 50)],
        [FakeMemory("human", ["a fact"], 95), FakeMemory("persona", None, 0)],
    )

    assert [d.block_name for d in snapshot.block_defs] == ["human", "persona"]
    assert snapshot.blocks["human"].word_limit == 100
    assert snapshot.blocks["human"].lines == ["a fact"]
    assert snapshot.blocks["persona"].word_limit == 50
    assert snapshot.blocks["persona"].lines == []
    assert [b.block_name for b in snapshot.nearing_capacity] == ["human"]


def test_a_block_with_no_stored_content_is_not_reported_as_full():
    class FakeDef:
        block_name = "human"
        description = "Facts"
        word_limit = 100

    snapshot = CoreMemorySnapshot.of([FakeDef()], [])

    assert snapshot.blocks == {}
    assert snapshot.nearing_capacity == []
