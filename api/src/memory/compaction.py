"""
Memory compaction service for auto-compacting memory blocks.

When a memory block reaches capacity and the LLM doesn't take action,
this service automatically compacts the block by:
1. Archiving the original content
2. Summarizing via LLM
3. Replacing with summarized content
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from src.common import CAPACITY_WARNING_THRESHOLD, COMPACTION_TARGET
from .models import CoreMemory
from .repository import MemoryRepository

if TYPE_CHECKING:
    from src.llm.providers.base import LLMProvider

log = logging.getLogger(__name__)


class MemoryCompactionService:
    """
    Service for managing memory capacity and auto-compaction.

    Tracks warning turns and triggers compaction when LLM doesn't act.
    """

    TURNS_BEFORE_AUTO_COMPACT = 3

    def __init__(self, memory_repo: Optional[MemoryRepository] = None):
        self.memory_repo = memory_repo or MemoryRepository()

    def check_capacity_warnings(self, agent_id: str, user_id: str) -> list[dict]:
        """
        Check all memory blocks for capacity warnings.

        Returns:
            List of dicts with block info for blocks at/above warning threshold
        """
        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)
        memories = {
            m.block_name: m
            for m in self.memory_repo.get_all_core_memories(agent_id, user_id)
        }

        warnings = []
        for block_def in block_defs:
            memory = memories.get(block_def.block_name)
            if memory:
                percent = memory.get_capacity_percent(block_def.word_limit)
                if percent >= CAPACITY_WARNING_THRESHOLD * 100:
                    warnings.append({
                        "block_name": block_def.block_name,
                        "word_count": memory.word_count,
                        "word_limit": block_def.word_limit,
                        "percent": percent,
                    })
        return warnings

    def build_warning_message(self, warnings: list[dict]) -> str:
        """
        Build a system message to warn the LLM about capacity.

        Args:
            warnings: List of warning dicts from check_capacity_warnings

        Returns:
            Warning message string to inject into system prompt
        """
        if not warnings:
            return ""

        lines = [
            "<memory_warning>",
            "The following memory blocks are nearing capacity:",
        ]
        for w in warnings:
            lines.append(
                f"- [{w['block_name']}]: {w['word_count']}/{w['word_limit']} words "
                f"({w['percent']:.0f}%)"
            )

        lines.extend([
            "",
            "You should:",
            "1. Review and consolidate redundant information",
            "2. Move detailed information to archival memory",
            "3. Delete outdated entries",
            "",
            "If you don't take action, the system will auto-compact these blocks.",
            "</memory_warning>",
        ])
        return "\n".join(lines)

    def process_turn_warnings(
        self, agent_id: str, user_id: str, warnings: list[dict]
    ) -> list[str]:
        """
        Process warnings for a turn, incrementing counters.

        Returns:
            List of block names that need auto-compaction
        """
        blocks_to_compact = []

        for warning in warnings:
            block_name = warning["block_name"]
            turns = self.memory_repo.increment_warning_turns(agent_id, user_id, block_name)

            if turns >= self.TURNS_BEFORE_AUTO_COMPACT:
                blocks_to_compact.append(block_name)
                log.info(
                    f"Block [{block_name}] needs auto-compaction after {turns} warning turns"
                )

        # Reset warning turns for blocks that are now below threshold
        current_warning_blocks = {w["block_name"] for w in warnings}
        block_defs = self.memory_repo.get_block_definitions(agent_id, user_id)

        for block_def in block_defs:
            if block_def.block_name not in current_warning_blocks:
                # Check if we had warnings before
                if self.memory_repo.get_warning_turns(agent_id, user_id, block_def.block_name) > 0:
                    self.memory_repo.reset_warning_turns(agent_id, user_id, block_def.block_name)
                    log.info(f"Reset warning turns for [{block_def.block_name}]")

        return blocks_to_compact

    async def auto_compact_block(
        self,
        agent_id: str,
        user_id: str,
        block_name: str,
        provider: "LLMProvider",
        credentials: dict,
    ) -> str:
        """
        Automatically compact a memory block using LLM summarization.

        This:
        1. Archives the original content to archival memory
        2. Summarizes the content via LLM call
        3. Replaces block content with summary

        Args:
            agent_id: Agent ID
            user_id: User ID
            block_name: Name of the block to compact
            provider: LLM provider for summarization
            credentials: Provider credentials

        Returns:
            Status message describing the compaction
        """
        memory = self.memory_repo.get_core_memory(agent_id, user_id, block_name)
        block_def = self.memory_repo.get_block_definition(agent_id, user_id, block_name)

        if not memory or not memory.lines:
            return f"Block [{block_name}] is empty, no compaction needed."

        if not block_def:
            return f"Block [{block_name}] definition not found."

        # Calculate target word count
        target_words = int(block_def.word_limit * COMPACTION_TARGET)
        original_word_count = memory.word_count

        # Archive original content
        original_content = "\n".join(
            f"{i+1}: {line}" for i, line in enumerate(memory.lines)
        )
        self.memory_repo.insert_archival(
            agent_id,
            user_id,
            f"[Auto-archived from {block_name} compaction on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]\n\n{original_content}"
        )

        # Build summarization prompt
        prompt = f"""Summarize the following memory block to under {target_words} words while preserving all key facts.
Return ONLY the summarized facts, one fact per line, no numbering or prefixes.

[{block_name}] Memory Block:
{original_content}

Output the summarized facts, one per line:"""

        # Call LLM for summarization
        summary_chunks = []
        async for event in provider.stream_response(
            messages=[{"role": "user", "content": prompt}],
            credentials=credentials,
        ):
            if event.type == "text":
                summary_chunks.append(event.content)

        # Parse and save summarized content
        summarized_text = "".join(summary_chunks).strip()
        new_lines = [line.strip() for line in summarized_text.split("\n") if line.strip()]

        memory.lines = new_lines
        memory.word_count = memory.compute_word_count()
        memory.updated_at = datetime.now(timezone.utc)
        self.memory_repo.save_core_memory(memory)

        # Reset warning turns after compaction
        self.memory_repo.reset_warning_turns(agent_id, user_id, block_name)

        log.info(
            f"Compacted [{block_name}] from {original_word_count} to {memory.word_count} words"
        )

        return (
            f"Auto-compacted [{block_name}] from {original_word_count} to "
            f"{memory.word_count} words. Original content archived."
        )
