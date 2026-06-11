"""
OpenAI LLM Provider.

Uses OAuth-backed Codex/ChatGPT responses endpoint.
"""

import json
import logging
from uuid import uuid4
from typing import Any, AsyncIterator, Optional

import httpx

from src.auth.openai_oauth import OpenAICredentials, extract_account_id_from_access_token
from src.config.settings import settings
from .base import LLMEvent, LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gpt-5.5"
CODEX_INCLUDE_FIELDS = ["reasoning.encrypted_content"]


class OpenAIProvider(LLMProvider):
    """OpenAI provider using Responses API streaming."""

    def _extract_instructions_and_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        instructions_chunks: list[str] = []
        filtered_messages: list[dict] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role != "system":
                filtered_messages.append(msg)
                continue

            if isinstance(content, str) and content.strip():
                instructions_chunks.append(content.strip())
                continue

            if isinstance(content, list):
                for block in content:
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        instructions_chunks.append(text.strip())

        instructions = "\n\n".join(instructions_chunks).strip() or "You are a helpful assistant."
        return instructions, filtered_messages

    def _text_block_type_for_role(self, role: str) -> str:
        # Codex backend expects assistant history as output blocks.
        if role == "assistant":
            return "output_text"
        return "input_text"

    def _normalize_tools(self, tools: list[dict]) -> list[dict]:
        normalized = []
        for tool in tools:
            if tool.get("type") == "function":
                normalized.append(self._normalize_function_tool(tool))
                continue

            custom = tool.get("custom") or {}
            name = custom.get("name") or tool.get("name")
            if not name:
                continue

            parameters = (
                custom.get("input_schema")
                or custom.get("inputSchema")
                or custom.get("parameters")
                or tool.get("input_schema")
                or tool.get("inputSchema")
                or tool.get("parameters")
                or {"type": "object", "properties": {}}
            )

            normalized.append(
                self._normalize_function_tool(
                    {
                        "type": "function",
                        "name": name,
                        "description": custom.get("description") or tool.get("description", ""),
                        "parameters": parameters,
                    }
                )
            )
        return normalized

    def _normalize_function_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "type": "function",
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        }
        if "strict" in tool:
            normalized["strict"] = tool["strict"]
        return normalized

    def _request_headers(self, credentials: OpenAICredentials) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if settings.openai_oauth_originator:
            headers["originator"] = settings.openai_oauth_originator
        account_id = credentials.account_id or extract_account_id_from_access_token(credentials.access_token)
        if account_id:
            headers["ChatGPT-Account-ID"] = account_id
        session_id = str(uuid4())
        headers["session-id"] = session_id
        headers["thread-id"] = session_id
        return headers

    def _request_body(
        self,
        model_id: str,
        instructions: str,
        request_messages: list[dict],
        tools: list[dict] | None,
    ) -> dict[str, Any]:
        normalized_tools = self._normalize_tools(tools or [])
        return {
            "model": model_id,
            "instructions": instructions,
            "input": self._convert_messages(request_messages),
            "tools": normalized_tools,
            "tool_choice": "auto",
            # The Codex OAuth backend can emit multiple tool calls in a single
            # turn. This architecture has side-effecting tools such as memory
            # writes, so execute tool calls sequentially across loop iterations.
            "parallel_tool_calls": False,
            "reasoning": None,
            "store": False,
            "stream": True,
            "include": CODEX_INCLUDE_FIELDS,
            "text": {"verbosity": "medium"},
        }

    def _convert_messages(self, messages: list[dict]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            text_block_type = self._text_block_type_for_role(role)

            if isinstance(content, str):
                converted.append(
                    {
                        "role": role,
                        "content": [{"type": text_block_type, "text": content}],
                    }
                )
                continue

            if isinstance(content, list):
                blocks: list[dict[str, Any]] = []
                for block in content:
                    if "text" in block:
                        blocks.append({"type": text_block_type, "text": block["text"]})
                        continue

                    tool_use = block.get("toolUse")
                    if tool_use:
                        tool_name = tool_use.get("name", "")
                        tool_input = tool_use.get("input", {})
                        blocks.append(
                            {
                                "type": text_block_type,
                                "text": (
                                    f"[tool_call name={tool_name}] "
                                    f"{json.dumps(tool_input, ensure_ascii=True)}"
                                ),
                            }
                        )
                        continue

                    tool_result = block.get("toolResult")
                    if tool_result:
                        result_chunks = tool_result.get("content", [])
                        output_text = ""
                        for chunk in result_chunks:
                            if isinstance(chunk, dict) and "text" in chunk:
                                output_text += str(chunk["text"])
                        blocks.append(
                            {
                                "type": text_block_type,
                                "text": f"[tool_result] {output_text}",
                            }
                        )

                if blocks:
                    converted.append({"role": role, "content": blocks})

        return converted

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        model_id = model or DEFAULT_MODEL_NAME
        typed_credentials = OpenAICredentials.model_validate(credentials)
        instructions, request_messages = self._extract_instructions_and_messages(messages)
        body = self._request_body(model_id, instructions, request_messages, tools)

        call_state: dict[str, dict[str, Any]] = {}
        diagnostic_context = {
            "model": model_id,
            "message_count": len(messages),
            "input_count": len(body.get("input", [])),
            "tool_count": len(body.get("tools", [])),
            "tool_names": [tool.get("name") for tool in body.get("tools", [])],
        }

        log.info(
            "Calling OpenAI OAuth responses endpoint with model %s, %d messages, %d tools",
            model_id,
            len(messages),
            len(tools) if tools else 0,
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                settings.openai_oauth_responses_url,
                headers=self._request_headers(typed_credentials),
                json=body,
            ) as response:
                upstream_request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
                if not response.is_success:
                    error_text = await response.aread()
                    log.error(
                        "OpenAI OAuth responses HTTP error: status=%s request_id=%s context=%s",
                        response.status_code,
                        upstream_request_id,
                        diagnostic_context,
                    )
                    raise RuntimeError(
                        "OpenAI OAuth responses error"
                        f" ({response.status_code}, request_id={upstream_request_id}): "
                        f"{error_text.decode('utf-8', errors='ignore')}"
                    )

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta", "")
                        if delta:
                            yield LLMEvent(type="text", content=delta)

                    elif event_type == "response.output_item.added":
                        item = event.get("item", {})
                        if item.get("type") == "function_call":
                            item_id = item.get("id", "")
                            call_state[item_id] = {
                                "tool_use_id": item.get("call_id", ""),
                                "tool_name": item.get("name", ""),
                                "arguments": "",
                            }

                    elif event_type == "response.function_call_arguments.delta":
                        item_id = event.get("item_id", "")
                        delta = event.get("delta", "")
                        if item_id in call_state:
                            call_state[item_id]["arguments"] += delta

                    elif event_type == "response.function_call_arguments.done":
                        item_id = event.get("item_id", "")
                        state = call_state.get(item_id)
                        if not state:
                            continue

                        try:
                            tool_input = json.loads(state.get("arguments", "") or "{}")
                        except json.JSONDecodeError:
                            tool_input = {}

                        yield LLMEvent(
                            type="tool_use",
                            tool_use_id=state.get("tool_use_id", ""),
                            tool_name=state.get("tool_name", ""),
                            tool_input=tool_input,
                        )

                    elif event_type == "response.completed":
                        yield LLMEvent(type="stop", content="completed")

                    elif event_type == "error":
                        err = event.get("error") or {}
                        request_id = (
                            err.get("request_id")
                            or err.get("requestId")
                            or upstream_request_id
                        )
                        log.error(
                            "OpenAI stream error event: request_id=%s error_type=%s error_code=%s context=%s",
                            request_id,
                            err.get("type"),
                            err.get("code"),
                            diagnostic_context,
                        )
                        raise RuntimeError(f"OpenAI stream error (request_id={request_id}): {err}")
