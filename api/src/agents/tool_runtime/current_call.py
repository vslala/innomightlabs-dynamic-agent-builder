"""Which tool call is running."""

from __future__ import annotations

from contextvars import ContextVar

#: The id of the tool call being run, the same `tool_call_id` the call's audit record keeps, so a tool can file
#: what it produces under it. A context variable, not turn state: a turn runs several tools at once.
current_tool_call_id: ContextVar[str | None] = ContextVar("current_tool_call_id", default=None)
