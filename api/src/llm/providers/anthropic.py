from anthropic import AsyncAnthropic
from typing import AsyncIterator, Optional
import json

from src.llm.providers.base import LLMEvent, LLMProvider
import logging

log = logging.getLogger(__name__)

class AnthropicProvider(LLMProvider):
    
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

        # Separate system prompt from conversation messages
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                # Handle both string content and structured content
                content = msg["content"]
                if isinstance(content, str):
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": content,
                    })
                else:
                    # Already structured (list of content blocks)
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": content,
                    })

        # Build request parameters
        request_params = {
            "model": model_id,
            "messages": anthropic_messages,
            "max_tokens": 4096,  # Required parameter for Anthropic API
        }

        # Add system prompt if provided
        if system_prompt:
            request_params["system"] = system_prompt

        # Add tools if provided
        if tools:
            request_params["tools"] = tools

        log.info(
            f"Calling Anthropic API with model {model_id}, "
            f"{len(anthropic_messages)} messages, {len(tools) if tools else 0} tools"
        )

        try:
            # Call Anthropic streaming API
            async with client.messages.stream(**request_params) as stream:
                # Track current tool use block being accumulated
                current_tool_use = None

                async for event in stream:
                    # Handle text deltas
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield LLMEvent(type="text", content=event.delta.text)
                        
                        # Handle tool input deltas
                        elif hasattr(event.delta, "partial_json"):
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