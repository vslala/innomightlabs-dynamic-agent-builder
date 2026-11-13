"""Standing in for one LLM provider's chat client or catalog in a test.

Every lookup (`provider`, `find_provider`, the model pickers) reads `src.llm.providers.PROVIDERS`, so replacing a
provider's entry there reaches all of them, and the provider's other parts (credentials, refusal rule) stay real.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from src.llm import providers
from src.llm.models import ModelInfo
from src.llm.providers import Provider


class ListedModels:
    """A catalog that lists the given models and counts how often it was asked."""

    def __init__(self, models: list[ModelInfo] | Callable[[Any], list[ModelInfo]]):
        self.models = models
        self.listings = 0

    def list_models(self, provider_settings: Any) -> list[ModelInfo]:
        self.listings += 1
        return self.models(provider_settings) if callable(self.models) else list(self.models)


def use_provider(monkeypatch: pytest.MonkeyPatch, name: str, **parts: Any) -> Provider:
    """Replace parts of the provider called `name` (`chat=...`, `catalog=...`) for this test."""
    replaced = dataclasses.replace(providers.provider(name), **parts)
    # The current list, so replacing several providers in one test keeps the earlier replacements
    monkeypatch.setattr(
        providers, "PROVIDERS", tuple(replaced if candidate.name == name else candidate for candidate in providers.PROVIDERS)
    )
    return replaced


def use_chat_everywhere(monkeypatch: pytest.MonkeyPatch, chat: Any) -> None:
    """Every provider chats through `chat`: for tests about the turn, not about any one provider."""
    monkeypatch.setattr(
        providers, "PROVIDERS", tuple(dataclasses.replace(candidate, chat=chat) for candidate in providers.PROVIDERS)
    )
