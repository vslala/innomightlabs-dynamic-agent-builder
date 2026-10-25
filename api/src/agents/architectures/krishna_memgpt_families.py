"""Krishna MemGPT's tool families, in the order their prompt sections appear.

A new set of tools is a `ToolCategory`, its specs in the registry, and one entry here: triggered by a reference kind
the conversation holds, or by a condition on the turn. See docs/LLD-message-references-and-tool-families.md.
"""

from __future__ import annotations

from src.agents.tool_runtime.families import ToolFamily
from src.agents.tool_runtime.specs import ToolCategory
from src.skills.models import ActorKind

from .krishna_memgpt_prompt import core_skill_section, knowledge_base_section, mcp_section, skills_section

TOOL_FAMILIES: list[ToolFamily] = [
    ToolFamily(ToolCategory.NATIVE, when=lambda state: True),
    ToolFamily(
        ToolCategory.KNOWLEDGE,
        when=lambda state: bool(state.linked_kb_ids),
        prompt_section=lambda state: knowledge_base_section(len(state.linked_kb_ids)),
    ),
    ToolFamily(
        ToolCategory.SKILL,
        when=lambda state: bool(state.enabled_skills),
        prompt_section=lambda state: skills_section(state.enabled_skills, state.recent_skill_actions),
    ),
    ToolFamily(
        ToolCategory.MCP,
        when=lambda state: bool(state.enabled_mcp_connections),
        prompt_section=lambda state: mcp_section(
            state.enabled_mcp_connections, shared_by_owner=state.actor_kind != ActorKind.OWNER
        ),
    ),
    # Images aren't message references yet: the condition includes the account's Image Reading setting
    ToolFamily(ToolCategory.IMAGE, when=lambda state: state.image_input_available),
    ToolFamily(
        ToolCategory.DOCUMENT,
        triggered_by=frozenset({"document"}),
        # A linked knowledge base's files can be read at any time, attached or not
        when=lambda state: bool(state.linked_kb_ids),
        prompt_section=lambda state: core_skill_section("documents"),
    ),
]
