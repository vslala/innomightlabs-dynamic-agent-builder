"""Prompt construction for Krishna MemGPT.

We now build prompts via a small pipeline of loaders.
Start with a single loader to preserve behavior, then split into focused loaders.
"""

from __future__ import annotations

from src.agents.prompt_pipeline import PromptBuildInput, PromptPipeline
from src.memory import MemoryRepository

from .krishna_memgpt_prompt_loaders import KrishnaMemGPTPromptLoader


def build_krishna_memgpt_system_prompt(
    *,
    agent_persona: str,
    memory_repo: MemoryRepository,
    agent_id: str,
    user_id: str,
    kb_instructions: str | None = None,
    skills_addendum: str | None = None,
) -> str:
    pipeline = PromptPipeline(
        loaders=[
            KrishnaMemGPTPromptLoader(memory_repo=memory_repo),
        ]
    )

    return pipeline.build(
        PromptBuildInput(
            agent_persona=agent_persona,
            agent_id=agent_id,
            user_id=user_id,
            kb_instructions=kb_instructions,
            skills_addendum=skills_addendum,
        )
    )
