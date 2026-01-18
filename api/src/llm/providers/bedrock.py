"""
Amazon Bedrock LLM Provider.

Uses the Bedrock Converse API with AWS access key authentication.
"""

import json
import logging
from typing import AsyncIterator, Optional

import boto3

from .base import LLMProvider, LLMEvent

log = logging.getLogger(__name__)


# Default model name when none specified
DEFAULT_MODEL_NAME = "claude-sonnet-4"


class BedrockProvider(LLMProvider):
    """
    Amazon Bedrock provider using the Converse API.

    Uses AWS access key authentication (access_key_id:secret_access_key format).
    Supports streaming responses using converse_stream.
    Supports tool use with the Bedrock tool calling format.
    """

    # Bedrock region (eu-west-2 per project config)
    REGION = "eu-west-2"

    def get_model_id(self, model_name: Optional[str] = None) -> str:
        """
        Get the Bedrock model ID for a given model name.

        Fetches available models from Bedrock and finds the matching model ID.
        Falls back to default model if not found.
        """
        from src.llm.models import models_service

        if not model_name:
            model_name = DEFAULT_MODEL_NAME

        # Fetch available models and find matching one
        available_models = models_service.get_bedrock_models()

        for model in available_models:
            if model.model_name == model_name:
                return model.model_id

        # Fallback: return first available model or use default pattern
        if available_models:
            log.warning(f"Model '{model_name}' not found, using default: {available_models[0].model_name}")
            return available_models[0].model_id

        # Last resort fallback
        log.warning(f"No models available, using hardcoded default")
        return "us.anthropic.claude-sonnet-4-20250514-v1:0"

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
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
        model_id = self.get_model_id(model)
        # Extract credentials
        access_key = credentials.get("access_key")
        secret_key = credentials.get("secret_key")

        if not access_key or not secret_key:
            raise ValueError("Missing required credentials: 'access_key' and 'secret_key'")

        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        # Separate system prompt from conversation messages
        system_prompt = None
        bedrock_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                # Handle both string content and structured content
                content = msg["content"]
                if isinstance(content, str):
                    bedrock_messages.append({
                        "role": msg["role"],
                        "content": [{"text": content}],
                    })
                elif isinstance(content, list):
                    # Already structured (tool results etc.)
                    bedrock_messages.append({
                        "role": msg["role"],
                        "content": content,
                    })
                else:
                    # Assume it's a single content block
                    bedrock_messages.append({
                        "role": msg["role"],
                        "content": [content],
                    })

        # Build request parameters
        request_params = {
            "modelId": model_id,
            "messages": bedrock_messages,
        }

        # Add system prompt if provided
        if system_prompt:
            request_params["system"] = [{"text": system_prompt}]

        # Add tools if provided
        if tools:
            bedrock_tools = [
                {
                    "toolSpec": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "inputSchema": {"json": tool["parameters"]},
                    }
                }
                for tool in tools
            ]
            request_params["toolConfig"] = {"tools": bedrock_tools}

        log.info(
            f"Calling Bedrock converse_stream with model {model_id}, "
            f"{len(bedrock_messages)} messages, {len(tools) if tools else 0} tools"
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
                            # Parse the accumulated tool input JSON
                            try:
                                tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                            except json.JSONDecodeError:
                                log.warning(f"Failed to parse tool input: {current_tool_input_json}")
                                tool_input = {}

                            yield LLMEvent(
                                type="tool_use",
                                tool_use_id=current_tool_id,
                                tool_name=current_tool_name,
                                tool_input=tool_input,
                            )

                            # Reset tool tracking
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input_json = ""

                    # Handle message stop event
                    if "messageStop" in event:
                        stop_reason = event["messageStop"].get("stopReason", "")
                        log.info(f"Bedrock stream completed: {stop_reason}")
                        yield LLMEvent(type="stop", content=stop_reason)

                    # Handle metadata event (usage info)
                    if "metadata" in event:
                        usage = event["metadata"].get("usage", {})
                        log.info(
                            f"Bedrock usage - input tokens: {usage.get('inputTokens', 0)}, "
                            f"output tokens: {usage.get('outputTokens', 0)}"
                        )

        except Exception as e:
            log.error(f"Bedrock API error: {e}")
            raise

    def __repr__(self) -> str:
        return f"BedrockProvider(default_model={DEFAULT_MODEL_NAME}, region={self.REGION})"
