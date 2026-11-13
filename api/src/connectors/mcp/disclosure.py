"""What `list_mcp_tools` shows the agent of a connector's tools.

A connector with small schemas shows them all. A larger one shows an index of names and summaries, and the agent loads
the schemas it needs by name or by search, as `load_skill` does for a large skill (`src/skills/disclosure.py`). A
listing stays in the context for the rest of the turn, so every later model call pays for it again: two full listings
cost one 51-call run about 4.5 M input tokens (docs/LLD-agent-context-cost.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from src.common.keyword_search import rank, summarize

#: A connector whose tools' JSON fits this many characters is shown whole: an index would only cost another call.
INLINE_SCHEMA_CHARS = 8_000
SEARCH_LIMIT = 5
SUGGESTION_LIMIT = 3
LOAD_NOTE = (
    "Schemas not shown. Call list_mcp_tools with this mcp_id and tools=[...] for the tools you will use, "
    "or query='...' to search."
)

#: One connector's entry in the listing, beside its `mcp_id` and `name`.
Disclosed = dict[str, Any]


@dataclass(frozen=True)
class ToolRequest:
    #: The connector's tools this caller may call, whole.
    tools: list[dict[str, Any]]
    names: list[str] | None = None
    query: str | None = None


class ToolDisclosure(Protocol):
    def applies(self, request: ToolRequest) -> bool: ...

    def disclose(self, request: ToolRequest) -> Disclosed: ...


class NamedTools:
    """`tools=[...]`: exactly the tools asked for, and the nearest names for any the connector doesn't have."""

    def applies(self, request: ToolRequest) -> bool:
        return bool(request.names)

    def disclose(self, request: ToolRequest) -> Disclosed:
        by_name = {tool.get("name"): tool for tool in request.tools}
        wanted = list(dict.fromkeys(request.names or []))
        disclosed: Disclosed = {"tools": [by_name[name] for name in wanted if name in by_name]}
        unknown = [name for name in wanted if name not in by_name]
        if unknown:
            disclosed["unknown_tools"] = unknown
            disclosed["suggestions"] = [
                tool["name"] for tool in search_tools(request.tools, " ".join(unknown), SUGGESTION_LIMIT)
            ]
        return disclosed


class SearchedTools:
    """`query="..."`: the best keyword matches, whole."""

    def applies(self, request: ToolRequest) -> bool:
        return bool(request.query and request.query.strip())

    def disclose(self, request: ToolRequest) -> Disclosed:
        return {"tools": search_tools(request.tools, request.query or "", SEARCH_LIMIT)}


class AllTools:
    """A connector small enough to show whole."""

    def applies(self, request: ToolRequest) -> bool:
        return len(json.dumps(request.tools, ensure_ascii=True)) <= INLINE_SCHEMA_CHARS

    def disclose(self, request: ToolRequest) -> Disclosed:
        return {"tools": request.tools}


class ToolIndex:
    """Any other connector: names and summaries, no schemas."""

    def applies(self, request: ToolRequest) -> bool:
        return True

    def disclose(self, request: ToolRequest) -> Disclosed:
        index = [{"name": tool.get("name", ""), "summary": summarize(tool.get("description") or "")} for tool in request.tools]
        return {"tool_index": index, "note": LOAD_NOTE}


DISCLOSURES: list[ToolDisclosure] = [NamedTools(), SearchedTools(), AllTools(), ToolIndex()]


def disclose_tools(request: ToolRequest) -> Disclosed:
    return next(d for d in DISCLOSURES if d.applies(request)).disclose(request)


def search_tools(tools: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    return rank(tools, query, limit, _searchable_texts)


def _searchable_texts(tool: dict[str, Any]) -> list[tuple[str, int]]:
    return [(str(tool.get("name") or ""), 3), (str(tool.get("title") or ""), 2), (str(tool.get("description") or ""), 1)]
