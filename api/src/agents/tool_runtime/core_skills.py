"""Core skills: manifests whose actions every agent gets as tools, offered by a tool family instead of installed.

The manifest and its `actions.py` stay the one source of an action's name, description, schema and behaviour; here
they become tool specs of the family's category, run with the context an installed skill would get and no config.
See docs/LLD-message-references-and-tool-families.md, section 3.5.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.current_call import current_tool_call_id
from src.agents.tool_runtime.specs import BoundTool, ToolCategory, ToolSpec
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.runtime_context import action_context, as_tool_result

#: Each core skill, by manifest id, and the category its tools are offered in.
CORE_SKILL_CATEGORIES: dict[str, ToolCategory] = {"documents": ToolCategory.DOCUMENT}


def core_skill_tools(registry: SkillRegistry | None = None) -> list[BoundTool]:
    """Every core skill's actions, bound to run through the skill registry."""
    registry = registry or get_skill_registry()
    tools: list[BoundTool] = []
    for skill_id, category in CORE_SKILL_CATEGORIES.items():
        loaded = registry.core(skill_id)
        if loaded is None:
            raise ValueError(f"Core skill '{skill_id}' has no manifest with `core: true`")
        handler = partial(run_core_skill_tool, registry, skill_id)
        for action in loaded.manifest.actions:
            definition = {"name": action.name, "description": action.description, "parameters": action.input_schema}
            tools.append(BoundTool(ToolSpec(definition, category), handler))
    return tools


async def run_core_skill_tool(
    registry: SkillRegistry, skill_id: str, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState
) -> str:
    context = action_context(
        skill_id=skill_id,
        installed_skill_id=skill_id,
        agent_id=state.agent_id,
        account_id=state.account_id,
        owner_id=state.owner_id,
        owner_email=state.owner_email,
        actor_email=state.actor_email,
        actor_id=state.actor_id,
        actor_kind=state.actor_kind,
        conversation_id=state.conversation_id,
        user_message_id=state.user_message_id,
        tool_call_id=current_tool_call_id.get(),
    )
    result = await registry.execute_action(skill_id, tool_name, tool_input, config={}, context=context)
    return as_tool_result(result)


def core_skill_prompt(skill_id: str, registry: SkillRegistry | None = None) -> str:
    """The manifest's instructions, which come with its tools."""
    loaded = (registry or get_skill_registry()).core(skill_id)
    return loaded.manifest.system_prompt.strip() if loaded else ""
