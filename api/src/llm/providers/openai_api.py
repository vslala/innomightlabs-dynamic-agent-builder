"""
OpenAI API-key LLM Provider.

Calls the public OpenAI API (api.openai.com) with the user's own API key: a
project key, a service-account key, anything the platform issues. It speaks the
same Responses API as the Codex backend, so the request body, message conversion
and event stream all come from OpenAIProvider; only the endpoint and the key differ.
"""

from typing import AsyncIterator, Optional

from .base import LLMEvent
from .openai import OpenAIProvider

OPENAI_API_BASE_URL = "https://api.openai.com/v1"


class OpenAIAPIProvider(OpenAIProvider):
    """OpenAI provider for the public Responses API, authenticated with an API key."""

    endpoint_label = "OpenAI API"

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required credential: 'api_key'")
        async for event in self._stream_responses(
            f"{OPENAI_API_BASE_URL}/responses",
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            messages,
            tools,
            model,
        ):
            yield event
