"""
Native tool definitions for the memGPT architecture.

These tools are available to agents with the krishna-memgpt architecture
and provide memory read/write capabilities.
"""

CORE_MEMORY_READ = {
    "name": "core_memory_read",
    "description": "Read a core memory block. Returns numbered lines with capacity info. Use this to see what you currently remember.",
    "parameters": {
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "description": "Block name (e.g., 'human', 'persona', or custom block)"
            }
        },
        "required": ["block"]
    }
}

CORE_MEMORY_APPEND = {
    "name": "core_memory_append",
    "description": "Append a new line to a memory block. Duplicate lines are automatically skipped (idempotent).",
    "parameters": {
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "description": "Block name"
            },
            "content": {
                "type": "string",
                "description": "The content to append as a new line"
            }
        },
        "required": ["block", "content"]
    }
}

CORE_MEMORY_REPLACE = {
    "name": "core_memory_replace",
    "description": "Replace a specific line in a memory block. You MUST specify the exact line number. Use core_memory_read first to see current line numbers.",
    "parameters": {
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "description": "Block name"
            },
            "line_number": {
                "type": "integer",
                "description": "The line number to replace (1-indexed)"
            },
            "new_content": {
                "type": "string",
                "description": "The new content for this line"
            }
        },
        "required": ["block", "line_number", "new_content"]
    }
}

CORE_MEMORY_DELETE = {
    "name": "core_memory_delete",
    "description": "Delete a specific line from a memory block. Lines below will shift up. Use core_memory_read first to see current line numbers.",
    "parameters": {
        "type": "object",
        "properties": {
            "block": {
                "type": "string",
                "description": "Block name"
            },
            "line_number": {
                "type": "integer",
                "description": "The line number to delete (1-indexed)"
            }
        },
        "required": ["block", "line_number"]
    }
}

CORE_MEMORY_LIST_BLOCKS = {
    "name": "core_memory_list_blocks",
    "description": "List all memory blocks available to you, including their current capacity usage.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

ARCHIVAL_MEMORY_INSERT = {
    "name": "archival_memory_insert",
    "description": "Store information in archival memory for long-term recall. Duplicate content is automatically detected and returns existing entry (idempotent). Use this for detailed information that doesn't fit in core memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The memory content to store"
            }
        },
        "required": ["content"]
    }
}

ARCHIVAL_MEMORY_SEARCH = {
    "name": "archival_memory_search",
    "description": "Search your archival memory. Returns paginated results. Use 'page' parameter to load more results if you don't find what you're looking for.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (searches content)"
            },
            "page": {
                "type": "integer",
                "description": "Page number (default: 1, 5 results per page)",
                "default": 1
            }
        },
        "required": ["query"]
    }
}

RECALL_CONVERSATION = {
    "name": "recall_conversation",
    "description": (
        "Retrieve earlier messages from this conversation that are not in your "
        "current context. Use this when the user references something discussed "
        "earlier, like 'what we talked about before' or 'as I mentioned earlier'. "
        "Returns messages in reverse chronological order (most recent first)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "Page number (1 = most recent older messages, higher = further back). Default: 1",
                "default": 1
            }
        },
        "required": []
    }
}

KNOWLEDGE_BASE_SEARCH = {
    "name": "knowledge_base_search",
    "description": (
        "Search the linked knowledge bases for relevant information. Use this tool "
        "when the user asks questions that might be answered by documentation, FAQs, "
        "product information, or other content that has been crawled into the knowledge base. "
        "Returns the most relevant text chunks with their source URLs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query - a question or descriptive sentence about what you're looking for"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 3, max: 10)",
                "default": 3
            }
        },
        "required": ["query"]
    }
}


NATIVE_TOOLS = [
    CORE_MEMORY_READ,
    CORE_MEMORY_APPEND,
    CORE_MEMORY_REPLACE,
    CORE_MEMORY_DELETE,
    CORE_MEMORY_LIST_BLOCKS,
    ARCHIVAL_MEMORY_INSERT,
    ARCHIVAL_MEMORY_SEARCH,
    RECALL_CONVERSATION,
]

KNOWLEDGE_TOOLS = [
    KNOWLEDGE_BASE_SEARCH,
]

NATIVE_TOOLS_MAP = {tool["name"]: tool for tool in NATIVE_TOOLS + KNOWLEDGE_TOOLS}
