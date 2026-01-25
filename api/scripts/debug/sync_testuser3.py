#!/usr/bin/env python3
"""
Manually sync testuser3's subscription from Stripe.

Usage:
    DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
        python scripts/debug/sync_testuser3.py
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.payments.stripe.router import StripeClient, sync_subscription_to_db


async def main():
    print("Syncing testuser3@example.com subscription")
    print("=" * 60)

    # testuser3's details from logs
    customer_id = "cus_Tr0U5bkwkffrd5"
    subscription_id = "sub_1StITq9vlzhgFql1zoVaRvSn"
    invoice_id = "in_1StITo9vlzhgFql1AzNI6uSP"

    stripe = StripeClient()

    # Fetch subscription from Stripe
    print(f"Fetching subscription: {subscription_id}")
    subscription = await stripe.get(f"/subscriptions/{subscription_id}")
    print(f"✓ Found subscription: {subscription['id']}")
    print(f"  Status: {subscription.get('status')}")
    print(f"  Customer: {subscription.get('customer')}")
    print()

    # Fetch invoice for period dates
    print(f"Fetching invoice: {invoice_id}")
    invoice = await stripe.get(f"/invoices/{invoice_id}")
    print(f"✓ Found invoice: {invoice['id']}")
    print()

    # Sync to database
    print("Syncing to database...")
    result = await sync_subscription_to_db(
        subscription_data=subscription,
        subscription_id=subscription_id,
        customer_id=customer_id,
        invoice_data=invoice,
    )

    if result:
        print(f"✓ Successfully synced subscription!")
        print(f"  User: {result.user_email}")
        print(f"  Plan: {result.plan_name}")
        print(f"  Status: {result.status}")
        print(f"  Period Start: {result.current_period_start}")
        print(f"  Period End: {result.current_period_end}")
    else:
        print("❌ Sync failed - check logs for errors")


if __name__ == "__main__":
    asyncio.run(main())
