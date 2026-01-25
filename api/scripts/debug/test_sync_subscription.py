#!/usr/bin/env python3
"""
Test syncing a subscription from Stripe for testuser2.

Usage:
    DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
        python scripts/debug/test_sync_subscription.py
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.payments.stripe.router import StripeClient, sync_subscription_to_db


async def main():
    print("Testing subscription sync for testuser2@example.com")
    print("=" * 60)

    # testuser2's Stripe customer ID
    customer_id = "cus_Tr0D2PJAib5ABg"

    stripe = StripeClient()

    # Get active subscription from Stripe
    print(f"Fetching subscriptions for customer: {customer_id}")
    response = await stripe.get(f"/subscriptions?customer={customer_id}&status=active&limit=1")

    subscriptions = response.get("data", [])

    if not subscriptions:
        print("❌ No active subscriptions found in Stripe for this customer")
        return

    subscription = subscriptions[0]
    subscription_id = subscription["id"]

    print(f"✓ Found subscription: {subscription_id}")
    print(f"  Status: {subscription.get('status')}")
    print(f"  Metadata: {subscription.get('metadata')}")
    print()

    # Try to sync it
    print("Attempting to sync subscription to database...")
    try:
        result = await sync_subscription_to_db(
            subscription_data=subscription,
            subscription_id=subscription_id,
            customer_id=customer_id,
            invoice_data=None
        )

        if result:
            print(f"✓ Successfully synced subscription!")
            print(f"  Plan: {result.plan_name}")
            print(f"  Status: {result.status}")
            print(f"  Period Start: {result.current_period_start}")
            print(f"  Period End: {result.current_period_end}")
        else:
            print("❌ Sync returned None - check logs for errors")

    except Exception as e:
        print(f"❌ Error during sync: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
