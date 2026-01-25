#!/usr/bin/env python3
"""
Check subscription details for a user.

Usage:
    python scripts/debug/check_user_subscription.py testuser@example.com

    # Or with environment variables:
    DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
        python scripts/debug/check_user_subscription.py testuser@example.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.payments.subscriptions.repository import SubscriptionRepository


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_user_subscription.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    repo = SubscriptionRepository()

    print(f"Checking subscriptions for: {email}")
    print("=" * 60)

    subs = repo.list_by_user(email)
    print(f"Total subscriptions found: {len(subs)}")
    print()

    if subs:
        for i, sub in enumerate(subs, 1):
            print(f"Subscription #{i}:")
            print(f"  ID: {sub.subscription_id}")
            print(f"  Plan: {sub.plan_name}")
            print(f"  Status: {sub.status}")
            print(f"  Period Start: {sub.current_period_start}")
            print(f"  Period End: {sub.current_period_end}")
            print(f"  Cancel at period end: {sub.cancel_at_period_end}")
            print(f"  Created: {sub.created_at}")
            print(f"  Updated: {sub.updated_at}")
            print()
    else:
        print("❌ No subscriptions found for this user")


if __name__ == "__main__":
    main()
