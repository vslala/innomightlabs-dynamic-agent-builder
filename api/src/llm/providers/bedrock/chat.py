"""
Amazon Bedrock LLM Provider.

Uses the Bedrock Converse API with AWS access key authentication.
"""

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import boto3

from src.llm.messages import (
    ContentBlock,
    ImageBlock,
    TextBlock,
    ToolUseBlock,
    content_text,
    normalize_messages,
    split_system_messages,
)
from src.llm.tools import normalize_tool_definitions
from src.llm.chat import LLMEvent, LLMProvider, StopReason, stop_reason_of
from src.llm.providers.bedrock.catalog import BEDROCK_REGION, FALLBACK_MODELS, BedrockCatalog

log = logging.getLogger(__name__)

BEDROCK_STOP_REASONS: dict[str, StopReason] = {
    "max_tokens": "max_tokens",
    "guardrail_intervened": "content_filter",
    "content_filtered": "content_filter",
}


# Default model name when none specified
# Must be a model available in eu-west-2
DEFAULT_MODEL_NAME = "claude-3-7-sonnet"


@dataclass(frozen=True)
class BedrockMessageConversion:
    system_prompt: str | None
    messages: list[dict[str, Any]]


class BedrockProvider(LLMProvider):
    """
    Amazon Bedrock provider using the Converse API.

    Uses AWS access key authentication (access_key_id:secret_access_key format).
    Supports streaming responses using converse_stream.
    Supports tool use with the Bedrock tool calling format.
    """

    default_model = DEFAULT_MODEL_NAME

    def get_model_id(self, access_key: str, secret_key: str, model_name: Optional[str] = None) -> str:
        """
        Get the Bedrock model ID for a given model name.

        Fetches the models these keys can use and finds the matching model ID.
        Falls back to default model if not found.
        """
        if not model_name:
            model_name = DEFAULT_MODEL_NAME

        # Fetch available models and find matching one
        available_models = BedrockCatalog().list_models_with_keys(access_key, secret_key)

        for model in available_models:
            if model.model_name == model_name:
                return model.model_id

        # Fallback: return first available model or use default pattern
        if available_models:
            log.warning(f"Model '{model_name}' not found, using default: {available_models[0].model_name}")
            return available_models[0].model_id

        log.warning("No Bedrock models listed, using the first fallback model")
        return FALLBACK_MODELS[0].model_id

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
        *,
        cache_key: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        """
        Stream response from Bedrock using the Converse API.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            credentials: Dict with 'access_key' and 'secret_key' keys
            tools: Optional list of tool definitions for function calling
            model: Optional model name (e.g., 'claude-sonnet-4', 'claude-3.5-haiku')

        Yields:
            LLMEvent objects for text, tool_use, or stop
        """
        access_key = credentials.get("access_key")
        secret_key = credentials.get("secret_key")

        if not access_key or not secret_key:
            raise ValueError("Missing required credentials: 'access_key' and 'secret_key'")
        model_id = self.get_model_id(access_key, secret_key, model)

        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=BEDROCK_REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        converted_messages = self._convert_messages(messages)

        # Build request parameters
        request_params: dict[str, Any] = {
            "modelId": model_id,
            "messages": converted_messages.messages,
        }

        # Add system prompt if provided
        if converted_messages.system_prompt:
            request_params["system"] = [{"text": converted_messages.system_prompt}]

        # Add tools if provided
        if tools:
            request_params["toolConfig"] = {"tools": self._normalize_tools(tools)}

        log.info(
            f"Calling Bedrock converse_stream with model {model_id}, "
            f"{len(converted_messages.messages)} messages, {len(tools) if tools else 0} tools"
        )

        try:
            # Call Bedrock converse_stream API
            response = client.converse_stream(**request_params)

            # Track current tool use block being accumulated
            current_tool_id = None
            current_tool_name = None
            current_tool_input_json = ""

            # Process streaming response
            stream = response.get("stream")
            if stream:
                for event in stream:
                    # Handle content block start (text or tool_use)
                    if "contentBlockStart" in event:
                        start = event["contentBlockStart"].get("start", {})
                        if "toolUse" in start:
                            # Starting a tool use block
                            current_tool_id = start["toolUse"].get("toolUseId", "")
                            current_tool_name = start["toolUse"].get("name", "")
                            current_tool_input_json = ""
                            log.info(f"Tool use started: {current_tool_name}")

                    # Handle content block delta events (text or tool input)
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"].get("delta", {})

                        # Text chunk
                        if "text" in delta:
                            yield LLMEvent(type="text", content=delta["text"])

                        # Tool input JSON chunk
                        if "toolUse" in delta:
                            input_chunk = delta["toolUse"].get("input", "")
                            current_tool_input_json += input_chunk

                    # Handle content block stop (emit tool_use event if tool)
                    if "contentBlockStop" in event:
                        if current_tool_id and current_tool_name:
                            yield LLMEvent.tool_call(current_tool_id, current_tool_name, current_tool_input_json)

                            # Reset tool tracking
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input_json = ""

                    # Handle message stop event
                    if "messageStop" in event:
                        stop_reason = event["messageStop"].get("stopReason", "")
                        log.info(f"Bedrock stream completed: {stop_reason}")
                        yield LLMEvent(type="stop", content=stop_reason_of(stop_reason, BEDROCK_STOP_REASONS))

                    # Handle metadata event (usage info)
                    if "metadata" in event:
                        yield usage_event(event["metadata"].get("usage", {}))

        except Exception as e:
            log.error(f"Bedrock API error: {e}", exc_info=True)
            raise

    def __repr__(self) -> str:
        return f"BedrockProvider(default_model={DEFAULT_MODEL_NAME}, region={BEDROCK_REGION})"

    def _convert_messages(self, messages: list[dict]) -> BedrockMessageConversion:
        split = split_system_messages(normalize_messages(messages))
        bedrock_messages = [
            {
                "role": message.role,
                "content": [self._convert_content_block(block) for block in message.content],
            }
            for message in split.conversation
        ]
        return BedrockMessageConversion(
            system_prompt=split.system_prompt,
            messages=bedrock_messages,
        )

    def _normalize_tools(self, tools: list[dict]) -> list[dict[str, Any]]:
        return [tool.to_bedrock() for tool in normalize_tool_definitions(tools)]

    def _convert_content_block(self, block: ContentBlock) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"text": block.text}
        if isinstance(block, ImageBlock):
            return {"image": {"format": block.format, "source": {"bytes": block.data}}}
        if isinstance(block, ToolUseBlock):
            tool_use: dict[str, Any] = {
                "toolUseId": block.id,
                "name": block.name,
                "input": block.input,
            }
            if block.thought_signature:
                tool_use["thoughtSignature"] = block.thought_signature
            return {"toolUse": tool_use}
        return {
            "toolResult": {
                "toolUseId": block.tool_use_id,
                "content": [{"text": content_text(block.content)}],
            }
        }


def usage_event(usage: dict[str, Any]) -> LLMEvent:
    """Converse's `inputTokens` leaves out what it read from or wrote to the cache; `prompt_tokens` counts it all."""
    cache_read = int(usage.get("cacheReadInputTokens") or 0)
    cache_write = int(usage.get("cacheWriteInputTokens") or 0)
    return LLMEvent(
        type="usage",
        prompt_tokens=int(usage.get("inputTokens") or 0) + cache_read + cache_write,
        completion_tokens=int(usage.get("outputTokens") or 0),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )
