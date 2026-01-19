"""
Native tool handlers for the memGPT architecture.

Handles execution of memory tools with idempotency and capacity management.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from src.common import CAPACITY_WARNING_THRESHOLD
from src.memory import (
    MemoryRepository,
    CoreMemory,
    MemoryBlockDefinition,
)
from src.messages.repository import MessageRepository
from src.vectorstore.search import get_search_service

log = logging.getLogger(__name__)


def normalize_block_name(block_name: str) -> str:
    """
    Normalize block name to lowercase with underscores.

    LLMs sometimes use formats like "Human - Facts about the user" or
    "Important_Financial_Data" instead of "human" or "important_financial_data".
    This function normalizes these variations.

    Examples:
        "Human - Facts about the user" -> "human"
        "Important_Financial_Data" -> "important_financial_data"
        "My Custom Block" -> "my_custom_block"
    """
    # Extract just the block name if it contains " - " (description separator)
    if " - " in block_name:
        block_name = block_name.split(" - ")[0].strip()

    # Convert to lowercase
    block_name = block_name.lower()

    # Replace spaces and hyphens with underscores
    block_name = re.sub(r"[\s\-]+", "_", block_name)

    # Remove any characters that aren't alphanumeric or underscore
    block_name = re.sub(r"[^a-z0-9_]", "", block_name)

    # Remove leading/trailing underscores and collapse multiple underscores
    block_name = re.sub(r"_+", "_", block_name).strip("_")

    return block_name


class NativeToolHandler:
    """
    Handler for executing native memory tools.

    Provides idempotent operations and capacity warnings.
    """

    RECALL_PAGE_SIZE = 10
    KB_SEARCH_MAX_RESULTS = 10

    def __init__(self, memory_repo: Optional[MemoryRepository] = None):
        self.memory_repo = memory_repo or MemoryRepository()
        self.message_repo = MessageRepository()
        self._conversation_id: Optional[str] = None
        self._linked_kb_ids: list[str] = []

    def set_conversation_context(self, conversation_id: str) -> None:
        """Set conversation context for recall_conversation tool."""
        self._conversation_id = conversation_id

    def set_knowledge_base_context(self, kb_ids: list[str]) -> None:
        """Set linked knowledge base IDs for knowledge_base_search tool."""
        self._linked_kb_ids = kb_ids

    async def execute(
        self, tool_name: str, arguments: dict, agent_id: str
    ) -> str:
        """
        Execute a native tool and return the result string.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            agent_id: ID of the agent

        Returns:
            Result string to return to the LLM
        """
        handler = getattr(self, f"_handle_{tool_name}", None)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")
        result: str = await handler(arguments, agent_id)
        return result

    def _get_block_or_error(
        self, args: dict, agent_id: str
    ) -> tuple[str, Optional[MemoryBlockDefinition], Optional[str]]:
        """
        Get block definition or return error message.

        Returns:
            Tuple of (normalized_block_name, block_def, error_msg).
            If block exists, error_msg is None.
            If block doesn't exist, block_def is None and error_msg contains the error.
        """
        block_name = normalize_block_name(args["block"])
        block_def = self.memory_repo.get_block_definition(agent_id, block_name)
        if not block_def:
            return block_name, None, f"Error: Block [{block_name}] does not exist."
        return block_name, block_def, None

    def _format_capacity(
        self, memory: CoreMemory, block_def: MemoryBlockDefinition
    ) -> str:
        """Format capacity info, with warning if above threshold."""
        percent = memory.get_capacity_percent(block_def.word_limit)
        capacity_str = f"{memory.word_count}/{block_def.word_limit} words"
        if percent >= CAPACITY_WARNING_THRESHOLD * 100:
            return (
                f"{capacity_str}\n"
                f"⚠️ WARNING: Block at {percent:.0f}% capacity. "
                "Consider consolidating or moving data to archival memory."
            )
        return capacity_str

    async def _handle_core_memory_read(self, args: dict, agent_id: str) -> str:
        """Read a core memory block."""
        block_name, block_def, error = self._get_block_or_error(args, agent_id)
        if error:
            return error
        assert block_def is not None  # Type narrowing: error is None means block_def exists

        memory = self.memory_repo.get_core_memory(agent_id, block_name)

        if not memory or not memory.lines:
            return f"[{block_name}] Core Memory is empty."

        capacity = self._format_capacity(memory, block_def)
        lines_str = "\n".join(
            f"{i+1}: {line}" for i, line in enumerate(memory.lines)
        )
        return (
            f"[{block_name}] Core Memory ({len(memory.lines)} lines, {capacity}):\n"
            f"{lines_str}"
        )

    async def _handle_core_memory_append(self, args: dict, agent_id: str) -> str:
        """Append a new line to a memory block (idempotent)."""
        block_name, block_def, error = self._get_block_or_error(args, agent_id)
        if error:
            return error
        assert block_def is not None  # Type narrowing: error is None means block_def exists

        content = args["content"].strip()

        # Idempotency check
        existing_line = self.memory_repo.line_exists(agent_id, block_name, content)
        if existing_line is not None:
            return (
                f"Line already exists in [{block_name}] at line {existing_line}: "
                f'"{content}" (no change)'
            )

        # Get or create memory
        memory = self.memory_repo.get_core_memory(agent_id, block_name)
        if not memory:
            memory = CoreMemory(agent_id=agent_id, block_name=block_name)

        memory.lines.append(content)
        memory.word_count = memory.compute_word_count()
        memory.updated_at = datetime.now(timezone.utc)
        self.memory_repo.save_core_memory(memory)

        return (
            f'Appended to [{block_name}] at line {len(memory.lines)}: "{content}" '
            f"({memory.word_count}/{block_def.word_limit} words)"
        )

    async def _handle_core_memory_replace(self, args: dict, agent_id: str) -> str:
        """Replace a specific line in a memory block (idempotent)."""
        block_name, block_def, error = self._get_block_or_error(args, agent_id)
        if error:
            return error
        assert block_def is not None  # Type narrowing: error is None means block_def exists

        line_num = args["line_number"]
        new_content = args["new_content"].strip()

        memory = self.memory_repo.get_core_memory(agent_id, block_name)
        if not memory or line_num < 1 or line_num > len(memory.lines):
            return f"Error: Line {line_num} does not exist in [{block_name}]"

        old_content = memory.lines[line_num - 1]

        # Idempotency: same content = no change
        if old_content.strip() == new_content:
            return (
                f"Line {line_num} in [{block_name}] already contains: "
                f'"{new_content}" (no change)'
            )

        memory.lines[line_num - 1] = new_content
        memory.word_count = memory.compute_word_count()
        memory.updated_at = datetime.now(timezone.utc)
        self.memory_repo.save_core_memory(memory)

        return (
            f"Replaced line {line_num} in [{block_name}]:\n"
            f'  Old: "{old_content}"\n'
            f'  New: "{new_content}"'
        )

    async def _handle_core_memory_delete(self, args: dict, agent_id: str) -> str:
        """Delete a specific line from a memory block (idempotent)."""
        block_name, block_def, error = self._get_block_or_error(args, agent_id)
        if error:
            return error
        assert block_def is not None  # Type narrowing: error is None means block_def exists

        line_num = args["line_number"]
        memory = self.memory_repo.get_core_memory(agent_id, block_name)
        if not memory or line_num < 1 or line_num > len(memory.lines):
            # Idempotent: deleting non-existent line is success
            return f"Line {line_num} does not exist in [{block_name}] (no change)"

        deleted = memory.lines.pop(line_num - 1)
        memory.word_count = memory.compute_word_count()
        memory.updated_at = datetime.now(timezone.utc)
        self.memory_repo.save_core_memory(memory)

        return (
            f'Deleted line {line_num} from [{block_name}]: "{deleted}"\n'
            f"[{block_name}] now has {len(memory.lines)} lines "
            f"({memory.word_count}/{block_def.word_limit} words)"
        )

    async def _handle_core_memory_list_blocks(
        self, args: dict, agent_id: str
    ) -> str:
        """List all available memory blocks."""
        block_defs = self.memory_repo.get_block_definitions(agent_id)
        memories = {
            m.block_name: m
            for m in self.memory_repo.get_all_core_memories(agent_id)
        }

        if not block_defs:
            return "No memory blocks configured for this agent."

        lines = ["Available Memory Blocks:"]
        for block_def in block_defs:
            memory = memories.get(block_def.block_name)
            word_count = memory.word_count if memory else 0
            percent = (
                (word_count / block_def.word_limit) * 100
                if block_def.word_limit > 0
                else 0
            )
            warning = " ⚠️" if percent >= CAPACITY_WARNING_THRESHOLD * 100 else ""
            lines.append(
                f"- [{block_def.block_name}] {word_count}/{block_def.word_limit} words "
                f"({percent:.1f}%){warning} - {block_def.description}"
            )
        return "\n".join(lines)

    async def _handle_archival_memory_insert(
        self, args: dict, agent_id: str
    ) -> str:
        """Insert into archival memory (idempotent)."""
        content = args["content"]
        memory, is_new = self.memory_repo.insert_archival(agent_id, content)

        if is_new:
            return f"Stored in archival memory (id: {memory.memory_id})"
        else:
            return (
                f"Already exists in archival memory "
                f"(id: {memory.memory_id}, created: {memory.created_at.strftime('%Y-%m-%d')})"
            )

    async def _handle_archival_memory_search(
        self, args: dict, agent_id: str
    ) -> str:
        """Search archival memory with pagination."""
        query = args["query"]
        page = args.get("page", 1)
        page_size = 5

        results, total = self.memory_repo.search_archival(
            agent_id, query, page, page_size
        )
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        if not results:
            return f'No archival memories found for "{query}"'

        lines = [
            f'Archival Memory Search for "{query}" '
            f"(Page {page} of {total_pages}, {total} total):\n"
        ]
        for i, mem in enumerate(results, start=1):
            preview = (
                mem.content[:80] + "..." if len(mem.content) > 80 else mem.content
            )
            lines.append(f"[{i}] ({mem.created_at.strftime('%Y-%m-%d')}) {preview}")

        if page < total_pages:
            lines.append(f"\n(Use page={page + 1} for more)")

        return "\n".join(lines)

    async def _handle_recall_conversation(
        self, args: dict, agent_id: str
    ) -> str:
        """
        Retrieve earlier messages from the current conversation.

        This tool allows the LLM to access messages that are not in its
        current context due to session timeout boundaries.
        """
        if not self._conversation_id:
            return "Error: No conversation context available"

        page = args.get("page", 1)
        if page < 1:
            page = 1

        # Get all messages for this conversation (oldest first)
        all_messages = self.message_repo.find_by_conversation(self._conversation_id)

        if not all_messages:
            return "No earlier messages found in this conversation."

        total = len(all_messages)
        total_pages = (total + self.RECALL_PAGE_SIZE - 1) // self.RECALL_PAGE_SIZE

        # Paginate in reverse chronological order (newest first)
        # Page 1 = most recent messages, higher pages = older messages
        start_idx = max(0, total - (page * self.RECALL_PAGE_SIZE))
        end_idx = max(0, total - ((page - 1) * self.RECALL_PAGE_SIZE))

        page_messages = all_messages[start_idx:end_idx]
        page_messages.reverse()  # Most recent first within page

        if not page_messages:
            return "No more messages. You've reached the beginning of this conversation."

        lines = [
            f"Earlier Conversation (Page {page} of {total_pages}, {total} total messages):\n"
        ]

        for msg in page_messages:
            timestamp = msg.created_at.strftime("%I:%M %p, %b %d")
            role_label = "User" if msg.role == "user" else "Assistant"
            content_preview = (
                msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            )
            lines.append(f"[{timestamp}] {role_label}: {content_preview}")

        if page < total_pages:
            lines.append(f"\n(Use page={page + 1} to see older messages)")

        return "\n".join(lines)

    async def _handle_knowledge_base_search(
        self, args: dict, agent_id: str
    ) -> str:
        """Search linked knowledge bases for relevant content."""
        if not self._linked_kb_ids:
            return "No knowledge bases are linked to this agent."

        query = args.get("query", "").strip()
        if not query:
            return "Error: Query is required for knowledge base search."

        top_k = min(args.get("top_k", 3), self.KB_SEARCH_MAX_RESULTS)

        try:
            search_service = get_search_service()
            results = await search_service.search_multiple_kbs(
                query=query,
                kb_ids=self._linked_kb_ids,
                top_k=top_k,
                min_score=0.3,
            )

            if not results:
                return f'No relevant content found for: "{query}"'

            lines = [f'Knowledge Base Search Results for "{query}":\n']

            for i, result in enumerate(results, start=1):
                content_preview = result.content[:500]
                if len(result.content) > 500:
                    content_preview += "..."

                lines.append(
                    f"[{i}] (Score: {result.score:.2f}) {result.page_title}\n"
                    f"    Source: {result.source_url}\n"
                    f"    Content: {content_preview}\n"
                )

            return "\n".join(lines)

        except Exception as e:
            log.error(f"Knowledge base search failed: {e}", exc_info=True)
            return f"Error searching knowledge bases: {str(e)}"
