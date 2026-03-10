"""
OpenAI LLM Provider.

Uses OAuth-backed Codex/ChatGPT responses endpoint.
"""

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from src.auth.openai_oauth import OpenAICredentials
from src.config.settings import settings
from .base import LLMEvent, LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gpt-5.4"


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
                normalized.append(tool)
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
                {
                    "type": "function",
                    "name": name,
                    "description": custom.get("description") or tool.get("description", ""),
                    "parameters": parameters,
                }
            )
        return normalized

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
        access_token = typed_credentials.access_token
        instructions, request_messages = self._extract_instructions_and_messages(messages)

        body: dict[str, Any] = {
            "model": model_id,
            "instructions": instructions,
            "store": False,
            "input": self._convert_messages(request_messages),
            "stream": True,
        }

        if tools:
            body["tools"] = self._normalize_tools(tools)

        call_state: dict[str, dict[str, Any]] = {}

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
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if not response.is_success:
                    error_text = await response.aread()
                    raise RuntimeError(f"OpenAI OAuth responses error: {error_text.decode('utf-8', errors='ignore')}")

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
                        raise RuntimeError(f"OpenAI stream error: {err}")
