"""In-memory snapshots for prompt rendering.

A snapshot represents a *single consistent read* of memory state for a turn.
Load once in the orchestrator; prompt loaders render from this snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class CoreMemorySnapshot:
    block_defs: list[CoreMemoryBlockDefSnapshot]
    blocks: dict[str, CoreMemoryBlockSnapshot]
