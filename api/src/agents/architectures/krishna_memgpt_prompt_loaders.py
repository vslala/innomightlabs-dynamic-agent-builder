"""Krishna MemGPT prompt loaders.

Start with a single loader that preserves current behavior.
We'll split it into multiple focused loaders incrementally.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.context import PromptContext
from src.agents.prompt_pipeline import PromptBuildInput, PromptLoaderBase
from src.common import CAPACITY_WARNING_THRESHOLD
from src.memory import MemoryRepository


class IdentityLoader(PromptLoaderBase):
    id = "krishna_memgpt.identity"
    requires = ("agent_persona", "agent_id", "user_id")

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        timestamp_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")

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


class PersonaLoader(PromptLoaderBase):
    id = "krishna_memgpt.persona"
    requires = ("agent_persona",)

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        ctx.add_section(
            "persona",
            f"""<persona>
{inp.agent_persona}
</persona>""",
        )


class CoreMemoryLoader(PromptLoaderBase):
    id = "krishna_memgpt.core_memory"
    requires = ("agent_id", "user_id")

    def __init__(self, *, memory_repo: MemoryRepository):
        self._memory_repo = memory_repo

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        memory_content = self._build_core_memory(agent_id=inp.agent_id, user_id=inp.user_id)
        ctx.add_section(
            "core_memory",
            f"""<core_memory>
{memory_content}
</core_memory>""",
        )

    def _build_core_memory(self, *, agent_id: str, user_id: str) -> str:
        block_defs = self._memory_repo.get_block_definitions(agent_id, user_id)
        memories = {m.block_name: m for m in self._memory_repo.get_all_core_memories(agent_id, user_id)}

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


class MemoryToolsLoader(PromptLoaderBase):
    id = "krishna_memgpt.memory_tools"

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
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


class KnowledgeBaseLoader(PromptLoaderBase):
    id = "krishna_memgpt.knowledge_base"
    optional_requires = ("runtime.kb_count",)

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        kb_count = inp.runtime.kb_count or 0
        ctx.add_section(
            "knowledge_base",
            f"""<knowledge_base>
You have access to {kb_count} knowledge base(s) containing documentation, FAQs, and other content.

Use the knowledge_base_search tool when:
- The user asks about products, features, or services
- The user needs information that might be in documentation
- The user asks "how do I..." or "what is..." questions about topics covered in the knowledge base
- You're unsure about factual information that the knowledge base might contain

The tool will return relevant text chunks with source URLs. Use these to provide accurate, sourced answers.
</knowledge_base>""",
        )


class SkillsLoader(PromptLoaderBase):
    id = "krishna_memgpt.skills"
    optional_requires = ("runtime.enabled_skills",)

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        skills = inp.runtime.enabled_skills or []

        # Keep it compact: the runtime tool list is the source of truth.
        names = []
        for s in skills:
            sid = (s.get("skill_id") or s.get("id") or "").strip()
            if sid:
                names.append(sid)

        if not names:
            return

        skills_list = "\n".join(f"- {n}" for n in names)

        ctx.add_section(
            "skills",
            f"""<skills>
Enabled skills ({len(names)}):
{skills_list}

Use the provided skill tools when needed. If a skill action fails, read the tool error and either retry with corrected inputs or ask the user for the missing information.
</skills>""",
        )


class CapacityWarningsLoader(PromptLoaderBase):
    id = "krishna_memgpt.warnings"
    optional_requires = ("runtime.capacity_warnings",)

    def __init__(self, *, memory_repo: MemoryRepository):
        # kept for backwards-compat during migration; will be removed once all callers pass warnings in runtime
        self._memory_repo = memory_repo

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        warnings = inp.runtime.capacity_warnings or []
        if not warnings:
            return

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
        ctx.add_section("warnings", "\n".join(lines))
