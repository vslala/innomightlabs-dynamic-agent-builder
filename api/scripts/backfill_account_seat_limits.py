#!/usr/bin/env python3
"""
Gives every account with no seat limit the seats of its owner's plan.

Seat limits are written when an account is created and whenever its owner's plan changes
(`RateLimitService.sync_seat_limits`). Accounts created before that have none, and invitations refuse to invite into
an account without one (SEAT_LIMIT_UNAVAILABLE), unless a superuser owns it. This sets the limit those accounts
would have had: the owner's current plan's `limits.seats`, 0 (unlimited) for a superuser's.

Running it again is safe: an account that already has a seat limit is left alone.

Usage:
    uv run python scripts/backfill_account_seat_limits.py           # dry run: says what it would write
    uv run python scripts/backfill_account_seat_limits.py --apply   # write the limits

Uses the API's own settings (DYNAMODB_TABLE, DYNAMODB_ENDPOINT, AWS credentials, ENVIRONMENT for the pricing
config). Against production, run it through `railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.accounts.models import Account  # noqa: E402
from src.accounts.repository import AccountRepository  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.rate_limits.service import RateLimitService  # noqa: E402


def accounts_without_seat_limit(table: Any) -> Iterator[Account]:
    """Every account item with no `seat_limit`. A one-off script, so a scan is fine."""
    kwargs: dict[str, Any] = {"FilterExpression": Attr("sk").eq("Account#Metadata") & Attr("seat_limit").not_exists()}
    while True:
        response = table.scan(**kwargs)
        yield from (Account.from_dynamo_item(item) for item in response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def limits_to_write(accounts: Iterator[Account], repository: AccountRepository,
                    plans: RateLimitService) -> tuple[list[tuple[Account, int]], Counter[str]]:
    """Each account's seat limit, and why any other account was skipped."""
    skipped: Counter[str] = Counter()
    to_write: list[tuple[Account, int]] = []
    seats_of: dict[str, int] = {}  # owner user_id -> seats, so a person with many accounts is looked up once
    for account in accounts:
        if account.owner_id not in seats_of:
            owner = repository.get_member(account.account_id, account.owner_id)
            if owner is None:
                skipped["owner is not a member (no email to find their plan by)"] += 1
                continue
            seats_of[account.owner_id] = plans.seat_limit_for(owner.email)
        to_write.append((account, seats_of[account.owner_id]))
    return sorted(to_write, key=lambda pair: pair[0].account_id), skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the limits (default: dry run)")
    args = parser.parse_args()

    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    # Where this will read and write: a shell that exports a local DYNAMODB_ENDPOINT overrides what `railway run`
    # brings, and the first sign is a "table not found" or, worse, a write to the wrong table.
    print(f"table {settings.dynamodb_table} at {settings.dynamodb_endpoint or 'AWS ' + settings.aws_region}")
    repository = AccountRepository()
    to_write, skipped = limits_to_write(accounts_without_seat_limit(table), repository, RateLimitService())

    for account, seats in to_write:
        print(f"{'write' if args.apply else 'would write'}: account {account.account_id} ({account.name}) -> "
              f"{seats or 'unlimited'} seat(s)")
        if args.apply:
            repository.set_seat_limit(account.account_id, seats)
    for reason, count in sorted(skipped.items()):
        print(f"skipped {count}: {reason}")
    by_seats = Counter(seats for _, seats in to_write)
    summary = ", ".join(f"{count} with {seats or 'unlimited'}" for seats, count in sorted(by_seats.items()))
    print(f"{len(to_write)} account(s) {'given' if args.apply else 'to give'} a seat limit"
          + (f" ({summary})" if summary else ""))


if __name__ == "__main__":
    main()
