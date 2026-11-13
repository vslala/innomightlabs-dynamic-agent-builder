"""Chat through the public OpenAI API (api.openai.com) with the account's own key: a project key, a service-account
key, anything the platform issues."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from src.llm.chat import LLMEvent, LLMProvider
from src.llm.providers.openai.chat import CODEX_EXTRAS, DEFAULT_MODEL_NAME
from src.llm.wire.responses import bearer_headers, responses_body, stream_chat

OPENAI_API_BASE_URL = "https://api.openai.com/v1"


class OpenAIAPIProvider(LLMProvider):
    default_model = DEFAULT_MODEL_NAME

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        # The public API accepts the Codex reasoning fields and carries reasoning between turns the same way.
        body = responses_body(model or self.default_model, messages, tools, **CODEX_EXTRAS)
        async for event in stream_chat(
            f"{OPENAI_API_BASE_URL}/responses", bearer_headers(credentials), body, label="OpenAI API"
        ):
            yield event
