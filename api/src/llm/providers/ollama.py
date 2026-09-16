"""Ollama LLM Provider.

Talks to a user-supplied Ollama endpoint over its native chat API
(`POST /api/chat`), which streams newline-delimited JSON rather than SSE.
The native API is preferred over the OpenAI-compatible `/v1` surface because
the rest of the Ollama integration (embeddings, model discovery via
`/api/tags`) already speaks it, and it reports token counts directly.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, AsyncIterator, NoReturn, Optional

import httpx

from src.config.settings import settings
from src.llm.messages import TextBlock, ToolResultBlock, ToolUseBlock, normalize_messages
from src.llm.ollama import OllamaConnection
from src.llm.tools import normalize_tool_definitions
from .base import LLMEvent, LLMProvider

log = logging.getLogger(__name__)

CHAT_PATH = "/api/chat"

#: Ollama does not return tool-call ids, but the agent loop keys tool results
#: off them, so they are synthesized per call with a stable position-based id.
SYNTHETIC_TOOL_CALL_ID_PREFIX = "ollama-call"


@dataclass(frozen=True)
class OllamaRequestInput:
    model: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    think: Optional[bool] = None


class OllamaProvider(LLMProvider):
    """Ollama provider streaming the native `/api/chat` NDJSON protocol."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        # Injectable purely so tests can drive the client with httpx.MockTransport.
        self._transport = transport

    def _convert_messages(self, messages: list[dict]) -> list[dict[str, Any]]:
        """Convert provider-neutral messages into Ollama chat messages.

        Ollama takes the system prompt as an ordinary `system` message, tool
        calls as `tool_calls` on an assistant message, and each tool result as
        its own `tool` role message -- so one input message can expand into
        several output messages.
        """
        tool_names_by_id: dict[str, str] = {}
        converted: list[dict[str, Any]] = []

        for message in normalize_messages(messages):
            text_chunks: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            tool_results: list[ToolResultBlock] = []

            for block in message.content:
                if isinstance(block, TextBlock):
                    if block.text.strip():
                        text_chunks.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_names_by_id[block.id] = block.name
                    tool_calls.append({"function": {"name": block.name, "arguments": block.input}})
                else:
                    tool_results.append(block)

            # Results answer the preceding assistant turn, so they lead.
            for result in tool_results:
                entry: dict[str, Any] = {"role": "tool", "content": result.content}
                tool_name = tool_names_by_id.get(result.tool_use_id)
                if tool_name:
                    entry["tool_name"] = tool_name
                converted.append(entry)

            if text_chunks or tool_calls:
                entry = {"role": message.role, "content": "\n".join(text_chunks)}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                converted.append(entry)

        return converted

    def _normalize_tools(self, tools: Optional[list[dict]]) -> list[dict[str, Any]]:
        return [tool.to_ollama() for tool in normalize_tool_definitions(tools)]

    def _request_input(
        self,
        model_id: str,
        messages: list[dict],
        tools: Optional[list[dict]],
        think: Optional[bool] = None,
    ) -> OllamaRequestInput:
        return OllamaRequestInput(
            model=model_id,
            messages=self._convert_messages(messages),
            tools=self._normalize_tools(tools),
            think=think,
        )

    def _request_body(self, request_input: OllamaRequestInput) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request_input.model,
            "messages": request_input.messages,
            "stream": True,
        }
        # Some models reject an empty tools array, so omit the key entirely.
        if request_input.tools:
            body["tools"] = request_input.tools
        # Omitted (rather than defaulted) so a model's own default reasoning
        # behavior is preserved when the agent has no explicit preference.
        if request_input.think is not None:
            body["think"] = request_input.think
        return body

    @staticmethod
    def _extract_usage(chunk: Mapping[str, Any]) -> tuple[int, int]:
        """Best-effort token usage from a final (`done: true`) chunk."""
        try:
            prompt_tokens = int(chunk.get("prompt_eval_count", 0) or 0)
            completion_tokens = int(chunk.get("eval_count", 0) or 0)
            return prompt_tokens, completion_tokens
        except (TypeError, ValueError):
            log.warning("Failed to parse Ollama usage counts from final chunk", exc_info=True)
            return 0, 0

    @staticmethod
    def _tool_use_events(message: Mapping[str, Any], id_offset: int) -> list[LLMEvent]:
        """Build one tool_use event per tool call on a streamed message."""
        raw_calls = message.get("tool_calls")
        if not isinstance(raw_calls, list):
            return []

        events: list[LLMEvent] = []
        for position, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, dict):
                continue
            function = raw_call.get("function")
            if not isinstance(function, dict):
                continue
            tool_name = str(function.get("name") or "")
            if not tool_name:
                continue

            events.append(
                LLMEvent(
                    type="tool_use",
                    tool_use_id=str(raw_call.get("id") or "")
                    or f"{SYNTHETIC_TOOL_CALL_ID_PREFIX}-{id_offset + position}-{tool_name}",
                    tool_name=tool_name,
                    tool_input=OllamaProvider._tool_arguments(function.get("arguments")),
                )
            )
        return events

    @staticmethod
    def _tool_arguments(arguments: Any) -> dict[str, Any]:
        """Ollama sends arguments as an object; some builds send a JSON string."""
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                log.warning("Ollama tool arguments were not valid JSON; treating as empty")
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _raise_http_error(status_code: int, body: str, base_url: str, model_id: str) -> NoReturn:
        if status_code in (401, 403):
            raise RuntimeError(
                f"Ollama endpoint at {base_url} rejected the request (HTTP {status_code}). "
                "Check the API key configured for the Ollama provider in Settings."
            )
        if status_code == 404:
            raise RuntimeError(
                f"Ollama endpoint at {base_url} does not have model '{model_id}' (HTTP 404). "
                f"Pull it on the host with `ollama pull {model_id}`, or select a different model."
            )
        raise RuntimeError(f"Ollama request to {base_url} failed (HTTP {status_code}): {body}")

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        model_id = (model or "").strip()
        if not model_id:
            # Unlike the hosted providers there is no sensible default tag,
            # since available models depend on what the user has pulled.
            raise ValueError(
                "Ollama requires an explicit model. Select one in the agent's settings."
            )

        connection = OllamaConnection.from_credentials(credentials)
        think = credentials.get("think")
        body = self._request_body(
            self._request_input(model_id, messages, tools, think=think if isinstance(think, bool) else None)
        )

        log.info(
            "Calling Ollama at %s with model %s, %d messages, %d tools",
            connection.base_url,
            model_id,
            len(messages),
            len(tools) if tools else 0,
        )

        tool_calls_seen = 0
        async with httpx.AsyncClient(
            base_url=connection.base_url,
            timeout=settings.ollama_timeout_seconds,
            transport=self._transport,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    CHAT_PATH,
                    headers=connection.headers,
                    json=body,
                ) as response:
                    if not response.is_success:
                        error_body = (await response.aread()).decode("utf-8", errors="ignore")
                        log.error(
                            "Ollama chat HTTP error: status=%s endpoint=%s model=%s",
                            response.status_code,
                            connection.base_url,
                            model_id,
                        )
                        self._raise_http_error(
                            response.status_code, error_body, connection.base_url, model_id
                        )

                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line:
                            continue

                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            log.warning("Skipping malformed Ollama stream line")
                            continue
                        if not isinstance(chunk, dict):
                            continue

                        error = chunk.get("error")
                        if error:
                            log.error("Ollama stream reported an error: %s", error)
                            raise RuntimeError(f"Ollama stream error: {error}")

                        message = chunk.get("message")
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, str) and content:
                                yield LLMEvent(type="text", content=content)

                            for event in self._tool_use_events(message, tool_calls_seen):
                                tool_calls_seen += 1
                                yield event

                        if chunk.get("done"):
                            prompt_tokens, completion_tokens = self._extract_usage(chunk)
                            yield LLMEvent(
                                type="usage",
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )
                            yield LLMEvent(
                                type="stop",
                                content=str(chunk.get("done_reason") or "completed"),
                            )
            except httpx.RequestError as e:
                log.error(
                    "Could not reach Ollama endpoint %s: %s", connection.base_url, e, exc_info=True
                )
                raise RuntimeError(
                    f"Could not reach the Ollama endpoint at {connection.base_url}. "
                    "Check that the endpoint URL is correct and reachable from the server."
                ) from e
