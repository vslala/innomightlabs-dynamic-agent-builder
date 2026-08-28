"""Google Gemini LLM Provider."""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, cast

from google import genai
from google.genai import types

from src.llm.messages import (
    ChatMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    content_text,
    normalize_messages,
    split_system_messages,
)
from src.llm.tools import normalize_tool_definitions
from .base import LLMEvent, LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"


@dataclass(frozen=True)
class GeminiMessageConversion:
    system_instruction: str | None
    messages: list[types.Content]


class GeminiProvider(LLMProvider):
    """Google Gemini provider using google-genai generate_content streaming."""

    def _build_client(self, credentials: dict[str, Any]) -> genai.Client:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required credential: 'api_key'")
        return genai.Client(api_key=str(api_key))

    def _tool_result_response(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {"result": content}
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}

    def _convert_messages(self, messages: list[dict]) -> GeminiMessageConversion:
        split = split_system_messages(normalize_messages(messages))
        return self._convert_normalized_messages(
            split.system_prompt,
            split.conversation,
        )

    def _convert_normalized_messages(
        self,
        system_instruction: str | None,
        conversation_messages: list[ChatMessage],
    ) -> GeminiMessageConversion:
        tool_names_by_id: dict[str, str] = {}
        contents: list[types.Content] = []

        for message in conversation_messages:
            role = message.role
            gemini_role = "model" if role == "assistant" else "user"
            parts: list[types.Part] = []

            for block in message.content:
                parts.extend(self._convert_content_block(block, tool_names_by_id))

            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))

        return GeminiMessageConversion(
            system_instruction=system_instruction,
            messages=contents,
        )

    def _convert_content_block(
        self,
        block: TextBlock | ToolUseBlock | ToolResultBlock,
        tool_names_by_id: dict[str, str],
    ) -> list[types.Part]:
        if isinstance(block, TextBlock):
            return [types.Part.from_text(text=block.text)]

        if isinstance(block, ToolUseBlock):
            if block.id and block.name:
                tool_names_by_id[block.id] = block.name
            part = types.Part.from_function_call(name=block.name, args=block.input)
            if block.thought_signature:
                part.thought_signature = block.thought_signature
            return [part]

        name = tool_names_by_id.get(block.tool_use_id)
        if not name:
            raise ValueError(f"Cannot convert Gemini tool result without a tool name: {block}")
        return [
            types.Part.from_function_response(
                name=name,
                response=self._tool_result_response(content_text(block.content)),
            )
        ]

    def _normalize_tools(self, tools: list[dict] | None) -> list[types.Tool] | None:
        declarations: list[types.FunctionDeclaration] = []
        for normalized in normalize_tool_definitions(tools):
            declarations.append(
                types.FunctionDeclaration(
                    name=normalized.name,
                    description=normalized.description,
                    parameters_json_schema=normalized.input_schema,
                )
            )

        if not declarations:
            return None
        return [types.Tool(function_declarations=declarations)]

    def _chunk_finish_reason(self, chunk: types.GenerateContentResponse) -> str | None:
        if not chunk.candidates:
            return None
        finish_reason = chunk.candidates[0].finish_reason
        return str(finish_reason) if finish_reason else None

    def _chunk_parts(self, chunk: types.GenerateContentResponse) -> list[types.Part]:
        if not chunk.candidates:
            return []
        content = chunk.candidates[0].content
        if not content or not content.parts:
            return []
        return list(content.parts)

    def _events_from_chunk(
        self,
        chunk: types.GenerateContentResponse,
        seen_tool_calls: set[str],
    ) -> list[LLMEvent]:
        events: list[LLMEvent] = []
        for part in self._chunk_parts(chunk):
            if part.text:
                events.append(LLMEvent(type="text", content=part.text))

            if part.function_call:
                function_call = part.function_call
                tool_name = function_call.name or ""
                tool_input = dict(function_call.args or {})
                tool_use_id = function_call.id or self._synthetic_tool_use_id(tool_name, tool_input)
                if tool_use_id in seen_tool_calls:
                    continue
                seen_tool_calls.add(tool_use_id)
                events.append(
                    LLMEvent(
                        type="tool_use",
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        thought_signature=part.thought_signature,
                    )
                )
        return events

    def _synthetic_tool_use_id(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        payload = json.dumps(tool_input, sort_keys=True, ensure_ascii=True)
        return f"gemini-{tool_name}-{payload}"

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        model_id = model or DEFAULT_MODEL_NAME
        client = self._build_client(credentials)
        converted_messages = self._convert_messages(messages)
        gemini_tools = self._normalize_tools(tools)
        config = types.GenerateContentConfig(
            system_instruction=converted_messages.system_instruction,
            tools=gemini_tools,
            max_output_tokens=4096,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        log.info(
            "Calling Gemini API with model %s, %d messages, %d tools",
            model_id,
            len(converted_messages.messages),
            len(tools) if tools else 0,
        )

        try:
            stream_result = client.aio.models.generate_content_stream(
                model=model_id,
                contents=converted_messages.messages,
                config=config,
            )
            stream = await stream_result if inspect.isawaitable(stream_result) else stream_result
            seen_tool_calls: set[str] = set()
            stop_reason = "completed"

            async for chunk in cast(AsyncIterator[types.GenerateContentResponse], stream):
                finish_reason = self._chunk_finish_reason(chunk)
                if finish_reason:
                    stop_reason = finish_reason
                for event in self._events_from_chunk(chunk, seen_tool_calls):
                    yield event

            yield LLMEvent(type="stop", content=stop_reason)
        except Exception as e:
            log.error("Gemini API error: %s", e, exc_info=True)
            raise
