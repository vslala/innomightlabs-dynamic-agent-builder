"""Helpers for appending tool loop messages to provider context."""

from __future__ import annotations

from typing import Any


def append_assistant_tool_uses(
    context: list[dict[Any, Any]],
    *,
    iteration_text: str = "",
    tool_events: list[Any],
) -> None:
    assistant_content: list[dict[str, Any]] = []

    if iteration_text.strip():
        assistant_content.append({"text": iteration_text})

    for tool_event in tool_events:
        assistant_content.append(tool_use_block(tool_event))

    context.append({"role": "assistant", "content": assistant_content})


def append_user_tool_results(
    context: list[dict[Any, Any]],
    tool_results: list[dict[str, Any]],
) -> None:
    context.append({"role": "user", "content": tool_results})


def tool_use_block(tool_event: Any) -> dict[str, Any]:
    tool_use = {
        "toolUseId": tool_event.tool_use_id,
        "name": tool_event.tool_name,
        "input": tool_event.tool_input,
    }
    thought_signature = getattr(tool_event, "thought_signature", None)
    if thought_signature:
        tool_use["thoughtSignature"] = thought_signature
    return {"toolUse": tool_use}


def with_tool_result(exchange: list[dict[Any, Any]], tool_use_id: str, result: str) -> list[dict[Any, Any]]:
    """The exchange with one call's result replaced: how a paused turn learns what the person decided."""
    for message in reversed(exchange):
        for index, block in enumerate(message.get("content", [])):
            if isinstance(block, dict) and block.get("toolResult", {}).get("toolUseId") == tool_use_id:
                message["content"][index] = tool_result_block(tool_use_id, result)
                return exchange
    raise ValueError(f"The exchange has no result for tool call {tool_use_id}")


def tool_result_block(tool_use_id: str, result: str) -> dict[str, Any]:
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"text": result}],
        }
    }
