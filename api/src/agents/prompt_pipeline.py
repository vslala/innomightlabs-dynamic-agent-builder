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
class PromptRuntime:
    """Turn-specific, optional prompt inputs.

    This is intentionally separate from required identity inputs so optional
    sections can evolve without bloating the base input contract.
    """

    # Knowledge base
    kb_count: int | None = None

    # Skills
    enabled_skills: list[dict] | None = None

    # Memory snapshot + capacity warnings
    core_memory: object | None = None  # CoreMemorySnapshot (import avoided to keep prompt pipeline lightweight)
    capacity_warnings: list[dict] | None = None


@dataclass(frozen=True)
class PromptBuildInput:
    """Inputs available to prompt loaders.

    Keep this small; expand only when a refactor step needs it.
    """

    agent_persona: str
    agent_id: str
    user_id: str
    runtime: PromptRuntime = PromptRuntime()


class PromptBuildError(Exception):
    def __init__(self, *, loader_id: str, missing: list[str]):
        self.loader_id = loader_id
        self.missing = missing
        super().__init__(f"Prompt loader '{loader_id}' missing required inputs: {', '.join(missing)}")


class PromptLoaderBase:
    """Base class for prompt loaders.

    Contract:
    - id: stable identifier (used in logs/errors)
    - requires: field paths that must be present (fatal if missing)
    - optional_requires: field paths that, if missing, should cause the loader to be skipped
    - load(): writes blocks into PromptContext

    Field paths are dotted, e.g. "agent_id" or "runtime.kb_instructions".
    """

    id: str = "prompt_loader"
    requires: tuple[str, ...] = ()
    optional_requires: tuple[str, ...] = ()

    def load(self, *, ctx: PromptContext, inp: PromptBuildInput) -> None:  # pragma: no cover
        raise NotImplementedError


def _get_field(inp: PromptBuildInput, path: str):
    cur: object = inp
    for part in path.split("."):
        cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def _missing_required(inp: PromptBuildInput, required: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for path in required:
        value = _get_field(inp, path)
        if value is None:
            missing.append(path)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(path)
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

            missing_optional = _missing_required(inp, loader.optional_requires)
            if missing_optional and loader.optional_requires:
                # Explicitly skip loaders whose optional inputs aren't present.
                continue

            loader.load(ctx=ctx, inp=inp)
        return ctx.render()
