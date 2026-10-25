"""Prompt construction for Krishna MemGPT: the system prompt, and the sections its tool families add."""

from __future__ import annotations

from src.agents.models import MemoryCapacityWarning
from src.agents.prompts import render_prompt_section, render_system_prompt
from src.agents.tool_runtime.core_skills import core_skill_prompt
from src.connectors.mcp.models import AgentMCPConnectionResponse
from src.memory.snapshot import CoreMemorySnapshot
from src.skills.models import AgentSkill, LoadedSkillRuntimeResponse

SYSTEM_PROMPT_TEMPLATE = "krishna_memgpt_system_prompt.j2"
SECTIONS = "krishna_memgpt/sections"


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    conversation_context: str | None = None,
    core_memory: CoreMemorySnapshot | None = None,
    capacity_warnings: list[MemoryCapacityWarning] | None = None,
    tool_sections: list[str] | None = None,
) -> str:
    return render_system_prompt(
        SYSTEM_PROMPT_TEMPLATE,
        has_memory_tools=True,
        agent_persona=agent_persona,
        conversation_context=conversation_context,
        core_memory=core_memory,
        capacity_warnings=capacity_warnings or [],
        tool_sections=tool_sections or [],
    )


def knowledge_base_section(kb_count: int) -> str:
    return render_prompt_section(f"{SECTIONS}/knowledge_base.j2", kb_count=kb_count)


def skills_section(
    enabled_skills: list[AgentSkill], recent_skill_actions: list[LoadedSkillRuntimeResponse] | None = None
) -> str:
    return render_prompt_section(
        f"{SECTIONS}/skills.j2", enabled_skills=enabled_skills, recent_skill_actions=recent_skill_actions or []
    )


def core_skill_section(skill_id: str) -> str:
    """A core skill's instructions, in a tag named after it."""
    prompt = core_skill_prompt(skill_id)
    return f"<{skill_id}>\n{prompt}\n</{skill_id}>" if prompt else ""


def mcp_section(connections: list[AgentMCPConnectionResponse], *, shared_by_owner: bool = False) -> str:
    return render_prompt_section(
        f"{SECTIONS}/mcp_connectors.j2", enabled_mcp_connections=connections, mcp_shared_by_owner=shared_by_owner
    )
