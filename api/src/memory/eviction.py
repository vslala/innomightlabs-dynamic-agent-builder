"""Memory eviction strategies for core memory blocks.

This module provides a small strategy-pattern architecture to decide how to
handle memory block overflow when a block exceeds its configured word_limit.

Design goals:
- Pluggable strategies (LRU, FIFO, summarization/compaction, ...)
- Minimal branching in call sites: select strategy by name and apply
- Deterministic behavior for tests

NOTE: Current core memory stores content as a list of lines. To support LRU/FIFO
we maintain per-line metadata (created_at/last_accessed_at) in CoreMemory.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .models import CoreMemory, MemoryBlockDefinition

log = logging.getLogger(__name__)


@dataclass
class EvictionResult:
    evicted_lines: list[str]
    evicted_count: int
    final_word_count: int


class EvictionStrategy(ABC):
    """Base class for eviction strategies."""

    name: str

    @abstractmethod
    def evict_to_limit(self, memory: CoreMemory, word_limit: int) -> EvictionResult:
        """Mutate memory in-place to meet word_limit and return result."""
        raise NotImplementedError


class NoEvictionStrategy(EvictionStrategy):
    name = "none"

    def evict_to_limit(self, memory: CoreMemory, word_limit: int) -> EvictionResult:
        return EvictionResult(evicted_lines=[], evicted_count=0, final_word_count=memory.word_count)


class FIFOStrategy(EvictionStrategy):
    name = "fifo"

    def evict_to_limit(self, memory: CoreMemory, word_limit: int) -> EvictionResult:
        evicted: list[str] = []

        # Ensure metadata exists and is aligned
        memory.ensure_line_meta()

        while memory.word_count > word_limit and memory.lines:
            evicted.append(memory.lines.pop(0))
            memory.line_meta.pop(0)
            memory.word_count = memory.compute_word_count()

        return EvictionResult(evicted_lines=evicted, evicted_count=len(evicted), final_word_count=memory.word_count)


class LRUStrategy(EvictionStrategy):
    name = "lru"

    def evict_to_limit(self, memory: CoreMemory, word_limit: int) -> EvictionResult:
        evicted: list[str] = []

        memory.ensure_line_meta()

        def _key(i: int) -> datetime:
            meta = memory.line_meta[i]
            # last_accessed_at is the primary signal; fall back to created_at
            return (meta.last_accessed_at or meta.created_at)

        while memory.word_count > word_limit and memory.lines:
            # Find least-recently-used line index
            idx = min(range(len(memory.lines)), key=_key)
            evicted.append(memory.lines.pop(idx))
            memory.line_meta.pop(idx)
            memory.word_count = memory.compute_word_count()

        return EvictionResult(evicted_lines=evicted, evicted_count=len(evicted), final_word_count=memory.word_count)


def get_eviction_strategy(name: str) -> EvictionStrategy:
    name_norm = (name or "").strip().lower()
    strategies: dict[str, type[EvictionStrategy]] = {
        NoEvictionStrategy.name: NoEvictionStrategy,
        FIFOStrategy.name: FIFOStrategy,
        LRUStrategy.name: LRUStrategy,
        # Future: "compact" => summarization/compaction strategy
    }
    cls = strategies.get(name_norm, NoEvictionStrategy)
    return cls()


class MemoryEvictionService:
    """Apply configured eviction policy for a block definition."""

    def apply_if_needed(
        self,
        memory: CoreMemory,
        block_def: MemoryBlockDefinition,
        now: Optional[datetime] = None,
    ) -> EvictionResult:
        if now is None:
            now = datetime.now(timezone.utc)

        # Ensure metadata exists
        memory.ensure_line_meta(now=now)

        policy = (block_def.eviction_policy or "none").lower()
        strat = get_eviction_strategy(policy)

        # Ensure word_count is fresh before applying policy
        memory.word_count = memory.compute_word_count()

        if block_def.word_limit <= 0:
            return EvictionResult(evicted_lines=[], evicted_count=0, final_word_count=memory.word_count)

        result = strat.evict_to_limit(memory, block_def.word_limit)

        if result.evicted_count:
            log.info(
                f"Evicted {result.evicted_count} lines from [{block_def.block_name}] "
                f"using policy={policy}; final_word_count={result.final_word_count}/{block_def.word_limit}"
            )

        return result
