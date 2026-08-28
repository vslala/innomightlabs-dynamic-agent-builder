"""Native and knowledge tool specs for agent execution."""

from __future__ import annotations

from src.agents.tool_runtime.commands import (
    ToolCommandCategory,
    ToolCommandMetadata,
    ToolIdempotency,
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


READ_ONLY_NATIVE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.READ_ONLY,
    allow_parallel=True,
)
READ_ONLY_KNOWLEDGE = ToolCommandMetadata(
    category=ToolCommandCategory.KNOWLEDGE,
    idempotency=ToolIdempotency.READ_ONLY,
    allow_parallel=True,
)
IDEMPOTENT_MEMORY_WRITE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.IDEMPOTENT_WRITE,
    mutates_prompt_context=True,
)
IDEMPOTENT_NATIVE_WRITE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.IDEMPOTENT_WRITE,
)


NATIVE_TOOL_SPECS = [
    ToolSpec(CORE_MEMORY_READ, READ_ONLY_NATIVE, CoreMemoryReadInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_APPEND, IDEMPOTENT_MEMORY_WRITE, CoreMemoryAppendInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_REPLACE, IDEMPOTENT_MEMORY_WRITE, CoreMemoryReplaceInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_DELETE, IDEMPOTENT_MEMORY_WRITE, CoreMemoryDeleteInput, NativeToolContext),
    ToolSpec(CORE_MEMORY_LIST_BLOCKS, READ_ONLY_NATIVE, CoreMemoryListBlocksInput, NativeToolContext),
    ToolSpec(ARCHIVAL_MEMORY_INSERT, IDEMPOTENT_NATIVE_WRITE, ArchivalMemoryInsertInput, NativeToolContext),
    ToolSpec(ARCHIVAL_MEMORY_SEARCH, READ_ONLY_NATIVE, ArchivalMemorySearchInput, NativeToolContext),
    ToolSpec(RECALL_CONVERSATION, READ_ONLY_NATIVE, RecallConversationInput, NativeToolContext),
    ToolSpec(WAIT, READ_ONLY_NATIVE, WaitInput, NativeToolContext),
    ToolSpec(KNOWLEDGE_BASE_SEARCH, READ_ONLY_KNOWLEDGE, KnowledgeBaseSearchInput, NativeToolContext),
]
