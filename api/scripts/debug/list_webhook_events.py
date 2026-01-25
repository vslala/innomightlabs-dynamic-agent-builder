#!/usr/bin/env python3
"""
List recent webhook events from database.

Usage:
    python scripts/debug/list_webhook_events.py

    # Show last 20:
    python scripts/debug/list_webhook_events.py --limit 20
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db import get_dynamodb_resource
from src.config import settings


def main():
    limit = 10
    if "--limit" in sys.argv:
        try:
            idx = sys.argv.index("--limit")
            limit = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Invalid limit value")
            sys.exit(1)

    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    print(f"Recent webhook events (last {limit}):")
    print("=" * 60)

    response = table.scan()
    items = response.get("Items", [])

    # Filter webhook events
    webhook_events = [
        item for item in items if "WebhookEvent#" in item.get("sk", "")
    ]

    # Sort by created_at (most recent first)
    webhook_events.sort(
        key=lambda x: x.get("created_at", ""), reverse=True
    )

    # Take limit
    webhook_events = webhook_events[:limit]

    print(f"Total webhook events: {len(webhook_events)}")
    print()

    for event in webhook_events:
        event_id = event.get("event_id", "unknown")
        event_type = event.get("event_type", "unknown")
        created_at = event.get("created_at", "unknown")

        print(f"Event ID: {event_id}")
        print(f"  Type: {event_type}")
        print(f"  Created: {created_at}")
        print()


if __name__ == "__main__":
    main()
