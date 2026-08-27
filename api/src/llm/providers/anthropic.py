from anthropic import AsyncAnthropic
from typing import Any, AsyncIterator, Optional, cast

from src.llm.messages import (
    ChatMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    normalize_messages,
    split_system_messages,
)
from src.llm.providers.base import LLMEvent, LLMProvider
from src.llm.tools import normalize_anthropic_tools
import logging

log = logging.getLogger(__name__)

class AnthropicProvider(LLMProvider):
    def _extract_system_and_messages(self, messages: list[dict]) -> tuple[str | None, list[dict[str, Any]]]:
        system_prompt, conversation = split_system_messages(normalize_messages(messages))
        return system_prompt, self._convert_messages(conversation)

    def _convert_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [
            {
                "role": message.role,
                "content": [self._convert_content_block(block) for block in message.content],
            }
            for message in messages
        ]

    def _convert_content_block(self, block: TextBlock | ToolUseBlock | ToolResultBlock) -> dict[str, Any]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
        }

    def _normalize_tools(self, tools: list[dict]) -> list[dict]:
        return normalize_anthropic_tools(tools)
    
    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        """
        Stream response from Anthropic API directly.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            credentials: Dict with 'api_key' key
            tools: Optional list of tool definitions for function calling
            model: Optional model name (e.g., 'claude-sonnet-4-5', 'claude-haiku-4-5')

        Yields:
            LLMEvent objects for text, tool_use, or stop
        """
        model_id = model or "claude-sonnet-4-5-20250929"
        
        # Extract API key
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required credential: 'api_key'")

        client = AsyncAnthropic(api_key=api_key)

        system_prompt, anthropic_messages = self._extract_system_and_messages(messages)

        # Build request parameters
        request_params: dict[str, Any] = {
            "model": model_id,
            "messages": anthropic_messages,
            "max_tokens": 4096,  # Required parameter for Anthropic API
        }

        # Add system prompt if provided
        if system_prompt:
            request_params["system"] = system_prompt

        # Add tools if provided
        if tools:
            request_params["tools"] = self._normalize_tools(tools)

        log.info(
            f"Calling Anthropic API with model {model_id}, "
            f"{len(anthropic_messages)} messages, {len(tools) if tools else 0} tools"
        )

        try:
            # Call Anthropic streaming API
            async with client.messages.stream(**cast(Any, request_params)) as stream:
                # Track current tool use block being accumulated
                current_tool_use: dict[str, Any] | None = None

                async for event in stream:
                    # Handle text deltas
                    if event.type == "content_block_delta":
                        delta = event.delta
                        text_delta = getattr(delta, "text", None)
                        if text_delta is not None:
                            yield LLMEvent(type="text", content=text_delta)

                        # Handle tool input deltas
                        elif getattr(delta, "partial_json", None) is not None:
                            # Tool input is being streamed as partial JSON
                            pass  # Accumulate in content_block_stop

                    # Handle content block start (for tool use)
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                            current_tool_use = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input": ""
                            }
                            log.info(f"Tool use started: {event.content_block.name}")

                    # Handle content block stop (emit complete tool_use)
                    elif event.type == "content_block_stop":
                        if current_tool_use:
                            # Get the final complete message to extract tool input
                            final_message = await stream.get_final_message()
                            
                            # Find the matching tool use block
                            for content_block in final_message.content:
                                if hasattr(content_block, "type") and content_block.type == "tool_use":
                                    if content_block.id == current_tool_use["id"]:
                                        yield LLMEvent(
                                            type="tool_use",
                                            tool_use_id=content_block.id,
                                            tool_name=content_block.name,
                                            tool_input=content_block.input,
                                        )
                                        break
                            
                            current_tool_use = None

                    # Handle message stop event
                    elif event.type == "message_stop":
                        final_message = await stream.get_final_message()
                        stop_reason = final_message.stop_reason
                        log.info(f"Anthropic stream completed: {stop_reason}")
                        yield LLMEvent(type="stop", content=stop_reason or "empty")

                        # Log usage
                        usage = final_message.usage
                        log.info(
                            f"Anthropic usage - input tokens: {usage.input_tokens}, "
                            f"output tokens: {usage.output_tokens}"
                        )

        except Exception as e:
            log.error(f"Anthropic API error: {e}", exc_info=True)
            raise
