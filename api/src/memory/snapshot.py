"""In-memory snapshots for prompt rendering.

A snapshot represents a *single consistent read* of memory state for a turn.
Load once in the orchestrator; prompt loaders render from this snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

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
