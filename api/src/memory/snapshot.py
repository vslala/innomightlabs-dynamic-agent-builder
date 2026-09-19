"""In-memory snapshots for prompt rendering.

A snapshot represents a *single consistent read* of memory state for a turn.
Load once in the orchestrator; prompt loaders render from this snapshot.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from src.common import CAPACITY_WARNING_THRESHOLD


@dataclass(frozen=True)
class CoreMemoryBlockDefSnapshot:
    block_name: str
    description: str
    word_limit: int


@dataclass(frozen=True)
class CoreMemoryBlockSnapshot:
    block_name: str
    lines: list[str]
    word_count: int
    word_limit: int

    @property
    def fill_percent(self) -> float:
        """How full the block is, 0-100. A block with no limit is never full."""
        if not self.word_limit:
            return 0.0
        return (self.word_count / self.word_limit) * 100

    @property
    def nearing_capacity(self) -> bool:
        """Single source of truth for the capacity badge and the warning section."""
        return self.fill_percent >= CAPACITY_WARNING_THRESHOLD * 100


@dataclass(frozen=True)
class CoreMemorySnapshot:
    block_defs: list[CoreMemoryBlockDefSnapshot]
    blocks: dict[str, CoreMemoryBlockSnapshot]

    @classmethod
    def of(cls, block_defs: Iterable[Any], memories: Iterable[Any]) -> "CoreMemorySnapshot":
        """Build a snapshot from one read of the definitions and their contents.

        A block's word limit lives on its definition, so the two reads are
        joined here rather than leaving callers to look it up per block.
        """
        word_limits = {definition.block_name: definition.word_limit for definition in block_defs}
        return cls(
            block_defs=[
                CoreMemoryBlockDefSnapshot(
                    block_name=definition.block_name,
                    description=definition.description,
                    word_limit=definition.word_limit,
                )
                for definition in block_defs
            ],
            blocks={
                memory.block_name: CoreMemoryBlockSnapshot(
                    block_name=memory.block_name,
                    lines=list(memory.lines or []),
                    word_count=memory.word_count,
                    word_limit=word_limits.get(memory.block_name, 0),
                )
                for memory in memories
            },
        )

    @property
    def nearing_capacity(self) -> list[CoreMemoryBlockSnapshot]:
        """Blocks close enough to their limit to be worth telling the agent about."""
        blocks = (self.blocks.get(definition.block_name) for definition in self.block_defs)
        return [block for block in blocks if block and block.nearing_capacity]
