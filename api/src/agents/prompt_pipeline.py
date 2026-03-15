"""Prompt-building pipeline.

This is a small foundation to support multiple contributors ("loaders") adding
blocks to a PromptContext without turning prompt construction into one long
function.

We keep it intentionally minimal and explicit (ordered list), and evolve it
incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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


class PromptBuildError(Exception):
    def __init__(self, *, loader_id: str, missing: list[str]):
        self.loader_id = loader_id
        self.missing = missing
        super().__init__(f"Prompt loader '{loader_id}' missing required inputs: {', '.join(missing)}")


class PromptLoaderBase:
    """Base class for prompt loaders.

    Contract:
    - id: stable identifier (used in logs/errors)
    - requires: list of PromptBuildInput field names the loader expects to be populated
    - load(): writes blocks into PromptContext
    """

    id: str = "prompt_loader"
    requires: tuple[str, ...] = ()

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:  # pragma: no cover
        raise NotImplementedError


def _missing_required(inp: PromptBuildInput, required: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for field in required:
        value = getattr(inp, field, None)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


class PromptPipeline:
    def __init__(self, loaders: list[PromptLoaderBase]):
        self._loaders = loaders

    def build(self, inp: PromptBuildInput) -> str:
        ctx = PromptContext()
        for loader in self._loaders:
            missing = _missing_required(inp, loader.requires)
            if missing:
                raise PromptBuildError(loader_id=loader.id, missing=missing)
            loader.load(ctx=ctx, inp=inp)
        return ctx.render()
