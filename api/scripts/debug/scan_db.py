#!/usr/bin/env python3
"""
Scan database and show counts of different entity types.

Usage:
    python scripts/debug/scan_db.py

    # Show all items (verbose):
    python scripts/debug/scan_db.py --verbose
"""

import sys
from pathlib import Path
from collections import Counter

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db import get_dynamodb_resource
from src.config import settings


def main():
    verbose = "--verbose" in sys.argv

    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    print(f"Scanning table: {settings.dynamodb_table}")
    print(f"Endpoint: {settings.dynamodb_endpoint or 'AWS'}")
    print("=" * 60)

    response = table.scan()
    items = response.get("Items", [])

    print(f"Total items: {len(items)}")
    print()

    # Count by entity type
    entity_types = Counter()
    for item in items:
        sk = item.get("sk", "")
        if "#" in sk:
            entity_type = sk.split("#")[0]
        else:
            entity_type = "Unknown"
        entity_types[entity_type] += 1

    print("Entity breakdown:")
    for entity_type, count in sorted(entity_types.items()):
        print(f"  {entity_type}: {count}")

    if verbose:
        print()
        print("All items:")
        print("-" * 60)
        for item in items:
            pk = item.get("pk", "")
            sk = item.get("sk", "")
            print(f"PK: {pk}, SK: {sk}")

            # Show relevant fields for subscriptions
            if "Subscription#" in sk:
                print(f"  Plan: {item.get('plan_name')}, Status: {item.get('status')}")
                print(f"  Period: {item.get('current_period_start')} - {item.get('current_period_end')}")

            # Show user details
            elif "User#Metadata" in sk:
                print(f"  Name: {item.get('name')}, Stripe: {item.get('stripe_customer_id')}")

            print()


if __name__ == "__main__":
    main()
