#!/usr/bin/env python3
"""
Gives every account that could draw before an Image Generation setting that still draws.

Two cases (docs/LLD-llm-providers-and-image-models.md, §4.5 and phase 5):
- An account with no setting whose agents drew with their own model (a provider whose chat models drew). It gets a
  setting on that provider: the agent's model if the provider's catalog still says it draws, else the catalog's
  first drawing model. The most recently updated such agent decides.
- An account whose saved model the provider's catalog no longer lists as drawing (an OpenAI API chat model, once
  the API key draws with `gpt-image-*`). Its model becomes the catalog's first drawing model.

The catalogs are asked with each account's own credentials, so it needs the vendors reachable. Running it again is
safe: an account whose setting draws is left alone.

Usage:
    uv run python scripts/backfill_image_generation_settings.py           # dry run: says what it would write
    uv run python scripts/backfill_image_generation_settings.py --apply   # write the settings

Uses the API's own settings (DYNAMODB_TABLE, DYNAMODB_ENDPOINT, AWS credentials). Against production, run it
through `railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.agents.image_generation.settings import (  # noqa: E402
    ImageGenerationSettings,
    ImageGenerationSettingsRepository,
)
from src.agents.models import Agent  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.llm.models import ModelCapability  # noqa: E402
from src.llm.providers import PROVIDERS, find_provider  # noqa: E402
from src.settings.repository import ProviderSettingsRepository  # noqa: E402

#: Providers whose agents used to draw with their own chat model, before the account setting existed.
DREW_WITH_OWN_MODEL = frozenset(p.name for p in PROVIDERS if p.images is not None)


def agents(table: Any) -> Iterator[Agent]:
    yield from (Agent.from_dynamo_item(item) for item in _scan(table, "Agent"))


def saved_settings(table: Any) -> Iterator[ImageGenerationSettings]:
    yield from (ImageGenerationSettings.from_dynamo_item(item) for item in _scan(table, "ImageGenerationSettings"))


def settings_to_write(
    all_agents: Iterable[Agent],
    all_settings: Iterable[ImageGenerationSettings],
    provider_settings: ProviderSettingsRepository,
) -> tuple[list[ImageGenerationSettings], Counter[str]]:
    """The settings to write, and why each other account was skipped."""
    skipped: Counter[str] = Counter()
    to_write: list[ImageGenerationSettings] = []

    saved = {setting.account_id: setting for setting in all_settings}
    for setting in saved.values():
        if not setting.is_configured:
            continue
        drawing = _drawing_models(setting.account_id, str(setting.provider_name), provider_settings)
        if drawing is None:
            skipped[f"{setting.provider_name} is no longer configured"] += 1
        elif setting.model_name not in drawing:
            if drawing:
                to_write.append(setting.model_copy(update={"model_name": drawing[0]}))
            else:
                skipped[f"{setting.provider_name} lists no model that draws"] += 1

    newest: dict[str, Agent] = {}
    for agent in all_agents:
        if agent.agent_provider in DREW_WITH_OWN_MODEL and agent.agent_model and agent.account_id not in saved:
            current = newest.get(agent.account_id)
            if current is None or _last_change(agent) > _last_change(current):
                newest[agent.account_id] = agent
    for account_id, agent in sorted(newest.items()):
        drawing = _drawing_models(account_id, agent.agent_provider, provider_settings)
        if drawing is None:
            skipped[f"{agent.agent_provider} is no longer configured"] += 1
        elif not drawing:
            skipped[f"{agent.agent_provider} lists no model that draws"] += 1
        else:
            model = agent.agent_model if agent.agent_model in drawing else drawing[0]
            to_write.append(
                ImageGenerationSettings(
                    account_id=account_id, enabled=True, provider_name=agent.agent_provider, model_name=model
                )
            )
    return sorted(to_write, key=lambda setting: setting.account_id), skipped


def _drawing_models(
    account_id: str, provider_name: str, provider_settings: ProviderSettingsRepository
) -> list[str] | None:
    """The models the account's own catalog for the provider says draw, or None if it no longer has the provider."""
    configured = provider_settings.find_by_provider(account_id, provider_name)
    found = find_provider(provider_name)
    if not configured or not found:
        return None
    return [m.model_name for m in found.catalog.list_models(configured) if m.can(ModelCapability.IMAGE_GENERATION)]


def _scan(table: Any, entity_type: str) -> Iterator[dict[str, Any]]:
    kwargs: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq(entity_type)}
    while True:
        response = table.scan(**kwargs)
        yield from response.get("Items", [])
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def _last_change(agent: Agent) -> Any:
    return agent.updated_at or agent.created_at


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the settings (default: dry run)")
    args = parser.parse_args()

    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    image_settings = ImageGenerationSettingsRepository()
    to_write, skipped = settings_to_write(agents(table), saved_settings(table), ProviderSettingsRepository())

    for setting in to_write:
        print(f"{'write' if args.apply else 'would write'}: account {setting.account_id} -> "
              f"{setting.provider_name} / {setting.model_name}")
        if args.apply:
            image_settings.save(setting)
    for reason, count in sorted(skipped.items()):
        print(f"skipped {count}: {reason}")
    print(f"{len(to_write)} account(s) {'given' if args.apply else 'to give'} an Image Generation setting")


if __name__ == "__main__":
    main()
