"""Keeping persisted model choices working after vendors retire or withhold them.

Agents, Dream, smart suggestions and image reading store a model name. Vendors retire models and gate
them per account (Codex refused `gpt-5.5` for a ChatGPT-login account on 2026-10-15), so a stored name
goes stale with no change on our side. The stored name stays the user's preference: it is always tried
first. Only when the vendor refuses that model is the call retried once on the first suitable model in
the account's live catalog, and the swap is remembered for a while so later calls skip the doomed try.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Optional

import anthropic
from google.genai import errors as genai_errors

from src.llm.models import ModelInfo, find_model_source
from src.llm.providers.base import LLMEvent, LLMProvider
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

#: How long a refused model is swapped for its substitute before the preference is tried again.
SUBSTITUTE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class ModelRefusal:
    """How one vendor says "this model is not available to you", as opposed to any other failure."""

    provider_names: frozenset[str]
    matches: Callable[[Exception], bool]


def _openai_refuses_model(exc: Exception) -> bool:
    # openai.py raises RuntimeError("<label> responses error (<status>, ...): <body>"). The Codex backend says
    # "The '<model>' model is not supported when using Codex with a ChatGPT account"; the public API answers
    # `model_not_found` / "does not exist or you do not have access to it".
    text = str(exc)
    return "responses error (" in text and any(
        marker in text for marker in ("model_not_found", "model is not supported", "does not exist")
    )


def _ollama_refuses_model(exc: Exception) -> bool:
    return "does not have model" in str(exc)


#: Bedrock is absent: `BedrockProvider.get_model_id` already maps a missing model onto the live catalog.
MODEL_REFUSALS: tuple[ModelRefusal, ...] = (
    ModelRefusal(frozenset({"OpenAI", "OpenAIAPI"}), _openai_refuses_model),
    ModelRefusal(frozenset({"Anthropic"}), lambda exc: isinstance(exc, anthropic.NotFoundError)),
    ModelRefusal(frozenset({"Gemini"}), lambda exc: isinstance(exc, genai_errors.ClientError) and exc.code == 404),
    ModelRefusal(frozenset({"Ollama"}), _ollama_refuses_model),
)


def is_model_refusal(provider_name: str, exc: Exception) -> bool:
    return any(provider_name in rule.provider_names and rule.matches(exc) for rule in MODEL_REFUSALS)


def pick_substitute(
    catalog: Sequence[ModelInfo], *, refused: Optional[str], capabilities: Sequence[str] = ()
) -> Optional[str]:
    """The first catalog model (catalogs come in the vendor's recommended order) other than the refused one
    that has every required capability."""
    for model in catalog:
        if refused in (model.model_name, model.model_id):
            continue
        if all(capability in model.capabilities for capability in capabilities):
            return model.model_name
    return None


#: (provider, account, preferred model) -> (expires at, substitute). Per process, like the Codex catalog cache.
_substitutes: dict[tuple[str, str, str], tuple[float, str]] = {}


class ModelFallbackProvider(LLMProvider):
    """A provider that tries the requested model, then a catalog substitute if the vendor refuses it."""

    def __init__(
        self,
        inner: LLMProvider,
        provider_name: str,
        provider_settings: ProviderSettings,
        *,
        capabilities: Sequence[str] = (),
    ):
        self.inner = inner
        self.provider_name = provider_name
        self.provider_settings = provider_settings
        self.capabilities = tuple(capabilities)

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        key = (self.provider_name, self.provider_settings.account_id, model or "")
        remembered = _substitutes.get(key)
        attempt = remembered[1] if remembered and remembered[0] > time.monotonic() else model

        yielded = False
        try:
            async for event in self.inner.stream_response(messages, credentials, tools, attempt):
                yielded = True
                yield event
            return
        except Exception as exc:
            # Once text has streamed the caller has a partial answer; a retry would duplicate it.
            if yielded or not is_model_refusal(self.provider_name, exc):
                raise
            # No model chosen means the provider's own default was the one refused.
            refused = attempt or self.inner.default_model
            substitute = await self._substitute_for(refused)
            if not substitute:
                raise
            log.warning(
                "%s refused model %r for account %s; using %r instead: %s",
                self.provider_name, refused, self.provider_settings.account_id, substitute, exc,
            )
            _substitutes[key] = (time.monotonic() + SUBSTITUTE_TTL_SECONDS, substitute)

        async for event in self.inner.stream_response(messages, credentials, tools, substitute):
            yield event

    async def _substitute_for(self, refused: Optional[str]) -> Optional[str]:
        source = find_model_source(self.provider_name)
        if not source:
            return None
        # Catalog listing is blocking HTTP; keep it off the event loop.
        catalog = await asyncio.to_thread(source.load_models, self.provider_settings)
        return pick_substitute(catalog, refused=refused, capabilities=self.capabilities)
