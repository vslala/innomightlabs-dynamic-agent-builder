"""Chat with xAI's Grok through its Responses API (api.x.ai/v1/responses), with the account's xAI key."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from src.llm.chat import LLMEvent, LLMProvider
from src.llm.wire.responses import bearer_headers, responses_body, stream_chat

GROK_API_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL_NAME = "grok-4.7"


class GrokProvider(LLMProvider):
    default_model = DEFAULT_MODEL_NAME

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        # The common body only: xAI has no Codex `reasoning.encrypted_content` include and no `text.verbosity`.
        body = responses_body(model or self.default_model, messages, tools)
        async for event in stream_chat(f"{GROK_API_BASE_URL}/responses", bearer_headers(credentials), body, label="Grok"):
            yield event
