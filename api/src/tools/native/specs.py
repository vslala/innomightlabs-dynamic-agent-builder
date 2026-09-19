"""Native and knowledge tool specs for agent execution."""

from __future__ import annotations

from src.agents.tool_runtime.commands import (
    ToolCommandCategory,
    ToolCommandMetadata,
    ToolSpec,
)
from src.agents.tool_runtime.contexts import NativeToolContext
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


NATIVE = ToolCommandMetadata(category=ToolCommandCategory.NATIVE)
KNOWLEDGE = ToolCommandMetadata(category=ToolCommandCategory.KNOWLEDGE)
#: Core-memory writes only. Archival writes are not here on purpose: the system
#: prompt renders the core-memory snapshot, so only core memory goes stale.
MEMORY_WRITE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    mutates_prompt_context=True,
)


NATIVE_TOOL_SPECS = [
    ToolSpec(CORE_MEMORY_READ, NATIVE, CoreMemoryReadInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_APPEND, MEMORY_WRITE, CoreMemoryAppendInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_REPLACE, MEMORY_WRITE, CoreMemoryReplaceInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_DELETE, MEMORY_WRITE, CoreMemoryDeleteInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_LIST_BLOCKS, NATIVE, CoreMemoryListBlocksInput, NativeToolContext),
    ToolSpec(ARCHIVAL_MEMORY_INSERT, NATIVE, ArchivalMemoryInsertInput, NativeToolContext),
    ToolSpec(ARCHIVAL_MEMORY_SEARCH, NATIVE, ArchivalMemorySearchInput, NativeToolContext),
    ToolSpec(RECALL_CONVERSATION, NATIVE, RecallConversationInput, NativeToolContext),
    ToolSpec(WAIT, NATIVE, WaitInput, NativeToolContext),
    ToolSpec(KNOWLEDGE_BASE_SEARCH, KNOWLEDGE, KnowledgeBaseSearchInput, NativeToolContext),
]
