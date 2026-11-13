"""Chat through a ChatGPT sign-in: the Codex backend's Responses endpoint, with the admin's OAuth token."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Optional
from uuid import uuid4

from src.auth.openai_oauth import OpenAICredentials, extract_account_id_from_access_token
from src.config import settings
from src.llm.chat import LLMEvent, LLMProvider
from src.llm.wire.responses import responses_body, stream_chat

DEFAULT_MODEL_NAME = "gpt-5.5"

#: What the Codex backend expects beyond the common body: reasoning carried between turns as encrypted content, which
#: needs `reasoning.encrypted_content` included, and its text verbosity.
CODEX_EXTRAS: dict[str, Any] = {
    "reasoning": None,
    "include": ["reasoning.encrypted_content"],
    "text": {"verbosity": "medium"},
}


class OpenAIProvider(LLMProvider):
    default_model = DEFAULT_MODEL_NAME

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
        *,
        cache_key: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        body = responses_body(model or self.default_model, messages, tools, cache_key=cache_key, **CODEX_EXTRAS)
        headers = codex_headers(OpenAICredentials.model_validate(credentials), session_id=cache_key)
        async for event in stream_chat(settings.openai_oauth_responses_url, headers, body, label="OpenAI OAuth"):
            yield event


def codex_headers(credentials: OpenAICredentials, *, session_id: str | None = None) -> dict[str, str]:
    """The headers the Codex CLI sends: the token, its ChatGPT account, and the session. Like the CLI, a call that
    continues a conversation keeps its session (`session_id`, the conversation's cache key); a one-off call gets a
    fresh one."""
    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    if settings.openai_oauth_originator:
        headers["originator"] = settings.openai_oauth_originator
    account_id = credentials.account_id or extract_account_id_from_access_token(credentials.access_token)
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id
    session_id = session_id or str(uuid4())
    headers["session-id"] = session_id
    headers["thread-id"] = session_id
    return headers
