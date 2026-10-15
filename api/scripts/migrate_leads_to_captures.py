#!/usr/bin/env python3
"""
Moves the leads `register_lead` saved before the Leads module (KAN-97) into the account's captures.

They were stored as `Agent#{agent_id}` / `Lead#{created_at}#{lead_id}` (entity_type LeadSubmission), which nothing
reads. Each becomes an ad-hoc capture (no lead form) in its agent's account, keeping its id and time, and is then
deleted. Old leads are not counted towards the plan, so none of them is ever locked.

Running it again is safe: a lead already moved is a duplicate capture and is only cleaned up.

Usage:
    uv run python scripts/migrate_leads_to_captures.py           # dry run: counts what would move
    uv run python scripts/migrate_leads_to_captures.py --apply   # move them

Uses the API's own settings (DYNAMODB_TABLE, DYNAMODB_ENDPOINT, AWS credentials). Against production, run it
through `railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.agents.repository import AgentRepository  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.leads.models import Capture, LabelledAnswer, ad_hoc_form  # noqa: E402
from src.leads.repository import DuplicateCapture, LeadsRepository  # noqa: E402
from src.skills.models import ActorKind  # noqa: E402


def legacy_leads(table: Any) -> Iterator[dict[str, Any]]:
    kwargs: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq("LeadSubmission")}
    while True:
        response = table.scan(**kwargs)
        yield from response.get("Items", [])
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def as_capture(item: dict[str, Any], account_id: str, initial_status: str) -> Capture:
    form_inputs, answers = ad_hoc_form([LabelledAnswer.model_validate(answer) for answer in item.get("answers", [])])
    # The owner trying their own agent left leads too; they are test captures now
    by_owner = bool(item.get("actor_email")) and item.get("actor_email") == item.get("owner_email")
    return Capture(
        capture_id=item["lead_id"],
        account_id=account_id,
        form_name=item.get("form_label") or "Lead",
        form_inputs=form_inputs,
        answers=answers,
        agent_id=item["agent_id"],
        conversation_id=item.get("conversation_id") or None,
        actor_kind=ActorKind.OWNER if by_owner else ActorKind.VISITOR,
        actor_id=item.get("actor_id") or item.get("actor_email") or "unknown",
        actor_email=item.get("actor_email") or None,
        source="dashboard" if by_owner else "widget",
        status=initial_status,
        created_at=datetime.fromisoformat(item["created_at"]),
    )


def migrate(*, apply: bool) -> Counter[str]:
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    agents = AgentRepository()
    leads = LeadsRepository()
    outcome: Counter[str] = Counter()

    for item in legacy_leads(table):
        outcome["found"] += 1
        agent = agents.get(item["agent_id"])
        if agent is None:
            outcome["skipped: agent no longer exists"] += 1
            continue
        capture = as_capture(item, agent.account_id, leads.find_settings(agent.account_id).initial_status)
        if not apply:
            outcome["would move"] += 1
            continue
        try:
            leads.save_capture(capture)
            outcome["moved"] += 1
        except DuplicateCapture:
            outcome["already moved"] += 1
        table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})

    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="move the leads (default: dry run)")
    args = parser.parse_args()

    outcome = migrate(apply=args.apply)
    print(f"{'Applied' if args.apply else 'Dry run'} on table {settings.dynamodb_table}")
    for label, count in outcome.items():
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()
