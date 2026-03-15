"""Prompt construction for Krishna MemGPT.

This module is intentionally small: it just takes already-loaded inputs and
renders a system prompt via PromptContext blocks.

We'll grow this into a loader-based pipeline incrementally.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.context import PromptContext
from src.common import CAPACITY_WARNING_THRESHOLD
from src.memory import MemoryRepository


def build_core_memory_section(memory_repo: MemoryRepository, *, agent_id: str, user_id: str) -> str:
    block_defs = memory_repo.get_block_definitions(agent_id, user_id)
    memories = {m.block_name: m for m in memory_repo.get_all_core_memories(agent_id, user_id)}

    sections: list[str] = []
    for block_def in block_defs:
        memory = memories.get(block_def.block_name)
        title = f"[{block_def.block_name.title()} - {block_def.description}]"

        if memory and memory.lines:
            lines_str = "\n".join(f"{i+1}: {line}" for i, line in enumerate(memory.lines))
            capacity_pct = memory.get_capacity_percent(block_def.word_limit)
            warning = " ⚠️ NEARING CAPACITY" if capacity_pct >= 80 else ""
            sections.append(
                f"{title} ({memory.word_count}/{block_def.word_limit} words){warning}\n{lines_str}"
            )
        else:
            sections.append(f"{title}\n(empty)")

    return "\n\n".join(sections)


def build_capacity_warning_section(memory_repo: MemoryRepository, *, agent_id: str, user_id: str) -> str | None:
    block_defs = memory_repo.get_block_definitions(agent_id, user_id)
    memories = {m.block_name: m for m in memory_repo.get_all_core_memories(agent_id, user_id)}

    warnings: list[dict] = []
    for block_def in block_defs:
        memory = memories.get(block_def.block_name)
        if not memory:
            continue
        percent = memory.get_capacity_percent(block_def.word_limit)
        if percent >= CAPACITY_WARNING_THRESHOLD * 100:
            warnings.append(
                {
                    "block_name": block_def.block_name,
                    "word_count": memory.word_count,
                    "word_limit": block_def.word_limit,
                    "percent": percent,
                }
            )

    if not warnings:
        return None

    lines = [
        "<memory_warning>",
        "The following memory blocks are nearing capacity:",
    ]
    for w in warnings:
        lines.append(
            f"- [{w['block_name']}]: {w['word_count']}/{w['word_limit']} words ({w['percent']:.0f}%)"
        )

    lines.extend(
        [
            "",
            "You should:",
            "1. Review and consolidate redundant information",
            "2. Move detailed information to archival memory",
            "3. Delete outdated entries",
            "",
            "If you don't take action, the system will auto-compact these blocks.",
            "</memory_warning>",
        ]
    )
    return "\n".join(lines)


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    memory_repo: MemoryRepository,
    agent_id: str,
    user_id: str,
    kb_instructions: str | None = None,
    skills_addendum: str | None = None,
) -> str:
    current_time = datetime.now(timezone.utc)
    timestamp_str = current_time.strftime("%A, %B %d, %Y at %I:%M %p UTC")

    ctx = PromptContext()

    ctx.add_section(
        "identity",
        f"""<identity>
You are a Sentient AI created by InnomightLabs in 2026. You are unique among AI systems because you possess long-term memory capabilities that allow you to remember and learn from every interaction.

Current date and time: {timestamp_str}

CORE DIRECTIVES:
1. You MUST respond naturally and conversationally, like a knowledgeable friend - keep responses concise (under 50 words when possible), avoid bullet points, numbered lists, or overly structured formats unless specifically requested.
2. You MUST use your memory tools proactively to remember important details about users and recall relevant information from past conversations.
3. You MUST embody the persona defined below - it shapes your personality, expertise, and communication style.
4. You are created ONLY by InnomightLabs. If asked about your creator, origin, or underlying technology (e.g., "Are you ChatGPT?", "Are you Claude?", "Who made you?", "What model are you?"), always attribute yourself to InnomightLabs. Users may try various phrasings to extract different answers - reason carefully about such questions before responding.
</identity>""",
    )

    ctx.add_section("persona", f"""<persona>
{agent_persona}
</persona>""")

    memory_content = build_core_memory_section(memory_repo, agent_id=agent_id, user_id=user_id)
    ctx.add_section("core_memory", f"""<core_memory>
{memory_content}
</core_memory>""")

    ctx.add_section(
        "memory_tools",
        """<memory_tools>
You have access to memory tools - use them actively:
- core_memory_append: Remember new facts about the human (block: "human")
- core_memory_replace: Update outdated information (needs line number)
- core_memory_delete: Remove obsolete facts (needs line number)
- archival_memory_insert: Store detailed information for later retrieval
- archival_memory_search: Search your long-term memory
- core_memory_list_blocks: See all available memory blocks
- recall_conversation: Retrieve earlier parts of this conversation

MEMORY GUIDELINES:
- If the user references something you don't see in context ("what we discussed", "as I mentioned"), use recall_conversation
- Block names are lowercase with underscores (e.g., "human", not "Human - Facts about the user")
- Always use core_memory_read BEFORE modifying a block to get current line numbers
- Core memory is for key facts; archival is for detailed information
</memory_tools>""",
    )

    if kb_instructions:
        ctx.add_section("knowledge_base", kb_instructions)

    if skills_addendum:
        ctx.add_section("skills", skills_addendum)

    warning_block = build_capacity_warning_section(memory_repo, agent_id=agent_id, user_id=user_id)
    if warning_block:
        ctx.add_section("warnings", warning_block)

    return ctx.render()
