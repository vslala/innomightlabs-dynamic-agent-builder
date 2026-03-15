"""Prompt construction for Krishna MemGPT.

We now build prompts via a small pipeline of loaders.
Start with a single loader to preserve behavior, then split into focused loaders.
"""

from __future__ import annotations

from src.agents.prompt_pipeline import PromptBuildInput, PromptPipeline
from src.memory import MemoryRepository

from .krishna_memgpt_prompt_loaders import (
    CapacityWarningsLoader,
    CoreMemoryLoader,
    IdentityLoader,
    KnowledgeBaseLoader,
    MemoryToolsLoader,
    PersonaLoader,
    SkillsLoader,
)


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    memory_repo: MemoryRepository,
    agent_id: str,
    user_id: str,
    kb_count: int | None = None,
    enabled_skills: list[dict] | None = None,
    capacity_warnings: list[dict] | None = None,
) -> str:
    pipeline = PromptPipeline(
        loaders=[
            IdentityLoader(),
            PersonaLoader(),
            CoreMemoryLoader(memory_repo=memory_repo),
            MemoryToolsLoader(),
            KnowledgeBaseLoader(),
            SkillsLoader(),
            CapacityWarningsLoader(memory_repo=memory_repo),
        ]
    )

    from src.agents.prompt_pipeline import PromptRuntime

    # kb_count is now the source of truth; callers should pass the real count.

    return pipeline.build(
        PromptBuildInput(
            agent_persona=agent_persona,
            agent_id=agent_id,
            user_id=user_id,
            runtime=PromptRuntime(
                kb_count=kb_count,
                enabled_skills=enabled_skills,
                capacity_warnings=capacity_warnings,
            ),
        )
    )
