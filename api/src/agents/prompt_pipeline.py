"""Prompt-building pipeline.

This is a small foundation to support multiple contributors ("loaders") adding
blocks to a PromptContext without turning prompt construction into one long
function.

We keep it intentionally minimal and explicit (ordered list), and evolve it
incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.agents.context import PromptContext


@dataclass(frozen=True)
class PromptBuildInput:
    """Inputs available to prompt loaders.

    Keep this small; expand only when a refactor step needs it.
    """

    agent_persona: str
    agent_id: str
    user_id: str
    kb_instructions: str | None = None
    skills_addendum: str | None = None


class PromptLoader(Protocol):
    id: str

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:
        ...


class PromptPipeline:
    def __init__(self, loaders: list[PromptLoader]):
        self._loaders = loaders

    def build(self, inp: PromptBuildInput) -> str:
        ctx = PromptContext()
        for loader in self._loaders:
            loader.load(ctx=ctx, inp=inp)
        return ctx.render()
