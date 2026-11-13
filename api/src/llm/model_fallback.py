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
from collections.abc import AsyncIterator, Sequence
from typing import Optional

from src.llm.models import ModelInfo
from src.llm.providers.base import LLMEvent, LLMProvider
from src.llm.providers.provider import Provider
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

#: How long a refused model is swapped for its substitute before the preference is tried again.
SUBSTITUTE_TTL_SECONDS = 3600


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
        provider: Provider,
        provider_settings: ProviderSettings,
        *,
        capabilities: Sequence[str] = (),
    ):
        self.provider = provider
        self.provider_settings = provider_settings
        self.capabilities = tuple(capabilities)

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        key = (self.provider.name, self.provider_settings.account_id, model or "")
        remembered = _substitutes.get(key)
        attempt = remembered[1] if remembered and remembered[0] > time.monotonic() else model

        yielded = False
        try:
            async for event in self.provider.chat.stream_response(messages, credentials, tools, attempt):
                yielded = True
                yield event
            return
        except Exception as exc:
            # Once text has streamed the caller has a partial answer; a retry would duplicate it.
            if yielded or not self.provider.refuses_model(exc):
                raise
            # No model chosen means the provider's own default was the one refused.
            refused = attempt or self.provider.chat.default_model
            substitute = await self._substitute_for(refused)
            if not substitute:
                raise
            log.warning(
                "%s refused model %r for account %s; using %r instead: %s",
                self.provider.name, refused, self.provider_settings.account_id, substitute, exc,
            )
            _substitutes[key] = (time.monotonic() + SUBSTITUTE_TTL_SECONDS, substitute)

        async for event in self.provider.chat.stream_response(messages, credentials, tools, substitute):
            yield event

    async def _substitute_for(self, refused: Optional[str]) -> Optional[str]:
        # Catalog listing is blocking HTTP; keep it off the event loop.
        catalog = await asyncio.to_thread(self.provider.catalog.list_models, self.provider_settings)
        return pick_substitute(catalog, refused=refused, capabilities=self.capabilities)
