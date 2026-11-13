"""The Responses API: OpenAI's, which the ChatGPT sign-in's Codex backend and other vendors also speak.

Message and tool conversion and the chat event stream live here once. Each provider builds its own URL, headers and
request extras, and calls `stream_chat`.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from src.llm.messages import ImageBlock, TextBlock, ToolResultBlock, ToolUseBlock, normalize_messages, split_system_messages
from src.llm.chat import LLMEvent, StopReason, stop_reason_of
from src.llm.tools import normalize_tool_definitions
from src.llm.wire.sse import sse_events

log = logging.getLogger(__name__)

#: Reasons given in `response.incomplete`'s `incomplete_details`.
INCOMPLETE_REASONS: dict[str, StopReason] = {
    "max_output_tokens": "max_tokens",
    "content_filter": "content_filter",
}

DEFAULT_INSTRUCTIONS = "You are a helpful assistant."
CHAT_TIMEOUT_SECONDS = 60.0


def responses_body(
    model: str, messages: list[dict], tools: list[dict] | None, *, cache_key: str | None = None, **extra: Any
) -> dict[str, Any]:
    """A streamed, unstored request. `extra` carries what one backend adds (Codex's reasoning fields).

    `cache_key` goes as `prompt_cache_key`: OpenAI and xAI send the calls that share one to the same server's cache.
    Without it xAI may send a call to a server that never read its earlier prefix, and the call pays for all of it."""
    instructions, items = responses_input(messages)
    cache_routing = {"prompt_cache_key": cache_key} if cache_key else {}
    return {
        "model": model,
        "instructions": instructions,
        "input": items,
        "tools": responses_tools(tools),
        "tool_choice": "auto",
        # A turn can call several tools at once, and this agent's tools have side effects (memory writes), so they
        # run one at a time, across loop iterations.
        "parallel_tool_calls": False,
        "store": False,
        "stream": True,
        **cache_routing,
        **extra,
    }


def responses_input(messages: list[dict]) -> tuple[str, list[dict[str, Any]]]:
    """(instructions, input items). Text stays in chat messages; tool calls and their results become the API's own
    items. Sending them as text taught the model that a tool call is something it writes, so long tool runs ended with
    the model typing a call instead of making one. See LLD-agent-loop-lost-final-answer.md."""
    split = split_system_messages(normalize_messages(messages))
    items: list[dict[str, Any]] = []
    for message in split.conversation:
        # Assistant history goes back as the model's own output blocks
        text_type = "output_text" if message.role == "assistant" else "input_text"
        texts: list[dict[str, Any]] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                texts.append({"type": text_type, "text": block.text})
            elif isinstance(block, ImageBlock):
                texts.append(_input_image(block))
            else:
                # Text said before a call belongs before it, so flush it into a message first.
                items += _chat_message(message.role, texts)
                texts = []
                items.append(_tool_item(block))
        items += _chat_message(message.role, texts)
    return split.system_prompt or DEFAULT_INSTRUCTIONS, items


def responses_tools(tools: list[dict] | None) -> list[dict[str, Any]]:
    return [tool.to_openai() for tool in normalize_tool_definitions(tools or [])]


def bearer_headers(credentials: dict[str, Any]) -> dict[str, str]:
    """The headers for a vendor reached with an API key."""
    api_key = credentials.get("api_key")
    if not api_key:
        raise ValueError("Missing required credential: 'api_key'")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream"}


async def stream_chat(url: str, headers: dict[str, str], body: dict[str, Any], *, label: str) -> AsyncIterator[LLMEvent]:
    """One streamed call: text, tool calls, usage and exactly one stop. `label` names the backend in logs and errors."""
    call_state: dict[str, dict[str, Any]] = {}
    diagnostic_context = {
        "model": body.get("model"),
        "input_count": len(body.get("input", [])),
        "tool_count": len(body.get("tools", [])),
        "tool_names": [tool.get("name") for tool in body.get("tools", [])],
    }
    log.info(
        "Calling %s responses endpoint with model %s, %d input items, %d tools",
        label, body.get("model"), diagnostic_context["input_count"], diagnostic_context["tool_count"],
    )

    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            upstream_request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
            if not response.is_success:
                error_text = await response.aread()
                log.error(
                    "%s responses HTTP error: status=%s request_id=%s context=%s",
                    label, response.status_code, upstream_request_id, diagnostic_context,
                )
                raise RuntimeError(
                    f"{label} responses error ({response.status_code}, request_id={upstream_request_id}): "
                    f"{error_text.decode('utf-8', errors='ignore')}"
                )

            async for event in sse_events(response):
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        yield LLMEvent(type="text", content=delta)

                elif event_type == "response.output_item.added":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        call_state[item.get("id", "")] = {
                            "tool_use_id": item.get("call_id", ""),
                            "tool_name": item.get("name", ""),
                            "arguments": "",
                        }

                elif event_type == "response.function_call_arguments.delta":
                    state = call_state.get(event.get("item_id", ""))
                    if state:
                        state["arguments"] += event.get("delta", "")

                elif event_type == "response.function_call_arguments.done":
                    state = call_state.get(event.get("item_id", ""))
                    if not state:
                        continue
                    try:
                        tool_input = json.loads(state["arguments"] or "{}")
                    except json.JSONDecodeError:
                        tool_input = {}
                    yield LLMEvent(
                        type="tool_use",
                        tool_use_id=state["tool_use_id"],
                        tool_name=state["tool_name"],
                        tool_input=tool_input,
                    )

                elif event_type in ("response.completed", "response.incomplete"):
                    yield usage_event(event)
                    details = (event.get("response") or {}).get("incomplete_details") or {}
                    yield LLMEvent(type="stop", content=stop_reason_of(details.get("reason"), INCOMPLETE_REASONS))

                elif event_type == "response.failed":
                    err = (event.get("response") or {}).get("error") or {}
                    log.error(
                        "%s response failed: request_id=%s error=%s context=%s",
                        label, upstream_request_id, err, diagnostic_context,
                    )
                    raise RuntimeError(f"{label} response failed (request_id={upstream_request_id}): {err}")

                elif event_type == "error":
                    err = event.get("error") or {}
                    request_id = err.get("request_id") or err.get("requestId") or upstream_request_id
                    log.error(
                        "%s stream error event: request_id=%s error_type=%s error_code=%s context=%s",
                        label, request_id, err.get("type"), err.get("code"), diagnostic_context,
                    )
                    raise RuntimeError(f"{label} stream error (request_id={request_id}): {err}")


def usage_event(event: dict[str, Any]) -> LLMEvent:
    """The usage in a `response.completed` event. `input_tokens` already counts the cached tokens, which
    `input_tokens_details` breaks out. Zeros when it isn't there: usage is telemetry, so a shape the vendor changes
    must never break the stream."""
    response = event.get("response")
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return LLMEvent(type="usage")
    details = usage.get("input_tokens_details")
    cache = details if isinstance(details, dict) else {}
    try:
        return LLMEvent(
            type="usage",
            prompt_tokens=int(usage.get("input_tokens") or 0),
            completion_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(cache.get("cached_tokens") or 0),
            cache_write_tokens=int(cache.get("cache_write_tokens") or 0),
        )
    except (TypeError, ValueError):
        log.warning("Unreadable Responses usage payload: %s", usage)
        return LLMEvent(type="usage")


def responses_refuses_model(exc: Exception) -> bool:
    """`stream_chat` raises RuntimeError("<label> responses error (<status>, ...): <body>"). The Codex backend says
    "The '<model>' model is not supported when using Codex with a ChatGPT account"; the public API answers
    `model_not_found` / "does not exist or you do not have access to it"."""
    text = str(exc)
    return "responses error (" in text and any(
        marker in text for marker in ("model_not_found", "model is not supported", "does not exist")
    )


def _chat_message(role: str, texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"role": role, "content": texts}] if texts else []


def _input_image(block: ImageBlock) -> dict[str, Any]:
    data = base64.b64encode(block.data).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{block.media_type};base64,{data}", "detail": "auto"}


def _tool_item(block: ToolUseBlock | ToolResultBlock) -> dict[str, Any]:
    if isinstance(block, ToolUseBlock):
        return {
            "type": "function_call",
            "call_id": block.id,
            "name": block.name,
            "arguments": json.dumps(block.input, ensure_ascii=True),
        }
    return {"type": "function_call_output", "call_id": block.tool_use_id, "output": block.content}
