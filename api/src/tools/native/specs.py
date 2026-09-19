"""Native and knowledge tool specs for agent execution."""

from __future__ import annotations

from src.agents.tool_runtime.specs import ToolCategory, ToolSpec
from src.tools.native.contracts import (
    ArchivalMemoryInsertInput,
    ArchivalMemorySearchInput,
    CoreMemoryAppendInput,
    CoreMemoryDeleteInput,
    CoreMemoryListBlocksInput,
    CoreMemoryReadInput,
    CoreMemoryReplaceInput,
    KnowledgeBaseSearchInput,
    RecallConversationInput,
    WaitInput,
)
from src.tools.native.definitions import (
    ARCHIVAL_MEMORY_INSERT,
    ARCHIVAL_MEMORY_SEARCH,
    CORE_MEMORY_APPEND,
    CORE_MEMORY_DELETE,
    CORE_MEMORY_LIST_BLOCKS,
    CORE_MEMORY_READ,
    CORE_MEMORY_REPLACE,
    KNOWLEDGE_BASE_SEARCH,
    RECALL_CONVERSATION,
    WAIT,
)

def _memory_write(definition: dict, input_model: type) -> ToolSpec:
    """A core-memory write, which leaves the rendered system prompt stale.

    Archival writes are not memory writes for this purpose: the prompt renders
    the core-memory snapshot, so only core memory can go stale.
    """
    return ToolSpec(
        definition,
        ToolCategory.NATIVE,
        input_model,
        mutates_prompt_context=True,
    )


NATIVE_TOOL_SPECS = [
    ToolSpec(CORE_MEMORY_READ, ToolCategory.NATIVE, CoreMemoryReadInput),
    _memory_write(CORE_MEMORY_APPEND, CoreMemoryAppendInput),
    _memory_write(CORE_MEMORY_REPLACE, CoreMemoryReplaceInput),
    _memory_write(CORE_MEMORY_DELETE, CoreMemoryDeleteInput),
    ToolSpec(CORE_MEMORY_LIST_BLOCKS, ToolCategory.NATIVE, CoreMemoryListBlocksInput),
    ToolSpec(ARCHIVAL_MEMORY_INSERT, ToolCategory.NATIVE, ArchivalMemoryInsertInput),
    ToolSpec(ARCHIVAL_MEMORY_SEARCH, ToolCategory.NATIVE, ArchivalMemorySearchInput),
    ToolSpec(RECALL_CONVERSATION, ToolCategory.NATIVE, RecallConversationInput),
    ToolSpec(WAIT, ToolCategory.NATIVE, WaitInput),
    ToolSpec(KNOWLEDGE_BASE_SEARCH, ToolCategory.KNOWLEDGE, KnowledgeBaseSearchInput),
]
