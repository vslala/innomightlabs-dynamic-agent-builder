"""
Amazon Bedrock LLM Provider.

Uses the Bedrock Converse API with AWS access key authentication.
"""

import logging
from typing import AsyncIterator

import boto3

from .base import LLMProvider

log = logging.getLogger(__name__)


class BedrockProvider(LLMProvider):
    """
    Amazon Bedrock provider using the Converse API.

    Uses AWS access key authentication (access_key_id:secret_access_key format).
    Supports streaming responses using converse_stream.
    """

    # Claude 3.7 Sonnet model ID for Bedrock
    MODEL_ID = "anthropic.claude-3-7-sonnet-20250219-v1:0"

    # Bedrock region (eu-west-2 per project config)
    REGION = "eu-west-2"

    async def stream_response(
        self,
        messages: list[dict],
        api_key: str,
    ) -> AsyncIterator[str]:
        """
        Stream response from Bedrock using the Converse API.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            api_key: AWS credentials in "access_key_id:secret_access_key" format

        Yields:
            Text chunks from the model response
        """
        # Parse access key and secret key
        if ":" not in api_key:
            raise ValueError("Invalid API key format. Expected 'access_key_id:secret_access_key'")

        access_key_id, secret_access_key = api_key.split(":", 1)

        client = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.REGION,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

        # Separate system prompt from conversation messages
        system_prompt = None
        bedrock_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                # Bedrock expects content as a list of content blocks
                bedrock_messages.append(
                    {
                        "role": msg["role"],
                        "content": [{"text": msg["content"]}],
                    }
                )

        # Build request parameters
        request_params = {
            "modelId": self.MODEL_ID,
            "messages": bedrock_messages,
        }

        # Add system prompt if provided
        if system_prompt:
            request_params["system"] = [{"text": system_prompt}]

        log.info(
            f"Calling Bedrock converse_stream with model {self.MODEL_ID}, "
            f"{len(bedrock_messages)} messages"
        )

        try:
            # Call Bedrock converse_stream API
            response = client.converse_stream(**request_params)

            # Process streaming response
            stream = response.get("stream")
            if stream:
                for event in stream:
                    # Handle content block delta events (text chunks)
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"].get("delta", {})
                        if "text" in delta:
                            yield delta["text"]

                    # Handle message stop event
                    if "messageStop" in event:
                        log.info("Bedrock stream completed")

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
        return f"BedrockProvider(model={self.MODEL_ID}, region={self.REGION})"
