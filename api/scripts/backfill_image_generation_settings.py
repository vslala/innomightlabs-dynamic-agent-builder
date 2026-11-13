#!/usr/bin/env python3
"""
Gives accounts that drew through an OpenAI agent's own model an Image Generation setting, so they keep drawing.

Before the account setting existed, an agent on OpenAI or OpenAIAPI drew with its own model. That fallback is gone
(docs/LLD-llm-providers-and-image-models.md, §4.5): only the account's setting decides who draws. For each account
with no setting and at least one such agent whose provider is still configured, this writes the setting, turned on,
with that provider and the model of the account's most recently updated such agent.

Running it again is safe: an account that already has a setting is skipped.

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
from src.llm.providers import PROVIDERS  # noqa: E402
from src.settings.repository import ProviderSettingsRepository  # noqa: E402

#: The providers whose agents used to draw with their own model: the ones whose chat models host the drawing tool.
DREW_WITH_OWN_MODEL = frozenset(p.name for p in PROVIDERS if p.images is not None)


def agents(table: Any) -> Iterator[Agent]:
    kwargs: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq("Agent")}
    while True:
        response = table.scan(**kwargs)
        yield from (Agent.from_dynamo_item(item) for item in response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def settings_to_write(
    all_agents: Iterable[Agent],
    image_settings: ImageGenerationSettingsRepository,
    provider_settings: ProviderSettingsRepository,
) -> tuple[list[ImageGenerationSettings], Counter[str]]:
    """The settings to write, and why each other account was skipped."""
    candidates: dict[str, Agent] = {}
    skipped: Counter[str] = Counter()
    for agent in all_agents:
        if agent.agent_provider not in DREW_WITH_OWN_MODEL or not agent.agent_model:
            continue
        current = candidates.get(agent.account_id)
        if current is None or _last_change(agent) > _last_change(current):
            candidates[agent.account_id] = agent

    to_write = []
    for account_id, agent in sorted(candidates.items()):
        if image_settings.find_in_account(account_id):
            skipped["already has a setting"] += 1
        elif not provider_settings.find_by_provider(account_id, agent.agent_provider):
            skipped[f"{agent.agent_provider} is no longer configured"] += 1
        else:
            to_write.append(
                ImageGenerationSettings(
                    account_id=account_id,
                    enabled=True,
                    provider_name=agent.agent_provider,
                    model_name=agent.agent_model,
                )
            )
    return to_write, skipped


def _last_change(agent: Agent) -> Any:
    return agent.updated_at or agent.created_at


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the settings (default: dry run)")
    args = parser.parse_args()

    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    image_settings = ImageGenerationSettingsRepository()
    to_write, skipped = settings_to_write(agents(table), image_settings, ProviderSettingsRepository())

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
