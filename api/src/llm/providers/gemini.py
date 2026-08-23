"""Google Gemini LLM Provider."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, AsyncIterator, Optional, cast

from google import genai
from google.genai import types

from .base import LLMEvent, LLMProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"


class GeminiProvider(LLMProvider):
    """Google Gemini provider using google-genai generate_content streaming."""

    def _build_client(self, credentials: dict[str, Any]) -> genai.Client:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required credential: 'api_key'")
        return genai.Client(api_key=str(api_key))

    def _extract_system_and_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        system_chunks: list[str] = []
        conversation_messages: list[dict] = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role != "system":
                conversation_messages.append(message)
                continue

            if isinstance(content, str) and content.strip():
                system_chunks.append(content.strip())
                continue

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            system_chunks.append(text.strip())

        return "\n\n".join(system_chunks) or None, conversation_messages

    def _tool_result_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    chunks.append(str(item["text"]))
                else:
                    chunks.append(json.dumps(item, ensure_ascii=True))
            return "\n".join(chunks)
        return json.dumps(content, ensure_ascii=True)

    def _tool_result_response(self, tool_result: dict[str, Any]) -> dict[str, Any]:
        text = self._tool_result_text(tool_result.get("content", []))
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"result": text}
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[types.Content]]:
        system_instruction, conversation_messages = self._extract_system_and_messages(messages)
        tool_names_by_id: dict[str, str] = {}
        contents: list[types.Content] = []

        for message in conversation_messages:
            role = message.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"
            raw_content = message.get("content", "")
            parts: list[types.Part] = []

            if isinstance(raw_content, str):
                parts.append(types.Part.from_text(text=raw_content))
            elif isinstance(raw_content, list):
                for block in raw_content:
                    parts.extend(self._convert_content_block(block, tool_names_by_id))
            else:
                parts.append(types.Part.from_text(text=json.dumps(raw_content, ensure_ascii=True)))

            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))

        return system_instruction, contents

    def _convert_content_block(
        self,
        block: Any,
        tool_names_by_id: dict[str, str],
    ) -> list[types.Part]:
        if not isinstance(block, dict):
            return [types.Part.from_text(text=str(block))]

        if "text" in block:
            return [types.Part.from_text(text=str(block["text"]))]

        tool_use = block.get("toolUse")
        if isinstance(tool_use, dict):
            name = str(tool_use.get("name") or "")
            tool_input = tool_use.get("input") if isinstance(tool_use.get("input"), dict) else {}
            tool_use_id = str(tool_use.get("toolUseId") or tool_use.get("id") or name)
            if tool_use_id and name:
                tool_names_by_id[tool_use_id] = name
            part = types.Part.from_function_call(name=name, args=tool_input)
            thought_signature = tool_use.get("thoughtSignature") or tool_use.get("thought_signature")
            if isinstance(thought_signature, bytes):
                part.thought_signature = thought_signature
            return [part]

        tool_result = block.get("toolResult")
        if isinstance(tool_result, dict):
            tool_use_id = str(tool_result.get("toolUseId") or tool_result.get("id") or "")
            name = tool_names_by_id.get(tool_use_id) or str(tool_result.get("name") or "")
            if not name:
                raise ValueError(f"Cannot convert Gemini tool result without a tool name: {tool_result}")
            return [
                types.Part.from_function_response(
                    name=name,
                    response=self._tool_result_response(tool_result),
                )
            ]

        return [types.Part.from_text(text=json.dumps(block, ensure_ascii=True))]

    def _normalize_function_tool(self, tool: dict[str, Any]) -> dict[str, Any] | None:
        if tool.get("type") == "function":
            name = tool.get("name")
            description = tool.get("description", "")
            parameters = tool.get("parameters") or {"type": "object", "properties": {}}
        else:
            custom = tool.get("custom") or {}
            name = custom.get("name") or tool.get("name")
            description = custom.get("description") or tool.get("description", "")
            parameters = (
                custom.get("input_schema")
                or custom.get("inputSchema")
                or custom.get("parameters")
                or tool.get("input_schema")
                or tool.get("inputSchema")
                or tool.get("parameters")
                or {"type": "object", "properties": {}}
            )

        if not name:
            log.warning("Skipping Gemini tool without name: %s", tool)
            return None
        return {
            "name": name,
            "description": description,
            "parameters": parameters,
        }

    def _normalize_tools(self, tools: list[dict] | None) -> list[types.Tool] | None:
        declarations: list[types.FunctionDeclaration] = []
        for tool in tools or []:
            normalized = self._normalize_function_tool(tool)
            if not normalized:
                continue
            declarations.append(
                types.FunctionDeclaration(
                    name=normalized["name"],
                    description=normalized["description"],
                    parameters_json_schema=normalized["parameters"],
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
        system_instruction, gemini_messages = self._convert_messages(messages)
        gemini_tools = self._normalize_tools(tools)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            max_output_tokens=4096,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        log.info(
            "Calling Gemini API with model %s, %d messages, %d tools",
            model_id,
            len(gemini_messages),
            len(tools) if tools else 0,
        )

        try:
            stream_result = client.aio.models.generate_content_stream(
                model=model_id,
                contents=gemini_messages,
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
