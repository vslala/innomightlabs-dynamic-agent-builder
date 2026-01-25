#!/usr/bin/env python3
"""
Fix subscription billing periods by fetching invoice data from Stripe.

Usage:
    DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
        python scripts/debug/fix_subscription_periods.py testuser2@example.com
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.payments.stripe.router import StripeClient, extract_invoice_period
from src.payments.subscriptions.repository import SubscriptionRepository


async def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_subscription_periods.py <email>")
        sys.exit(1)

    email = sys.argv[1]

    print(f"Fixing subscription periods for: {email}")
    print("=" * 60)

    repo = SubscriptionRepository()
    subs = repo.list_by_user(email)

    if not subs:
        print("❌ No subscriptions found")
        return

    stripe = StripeClient()

    for sub in subs:
        print(f"\nSubscription: {sub.subscription_id}")
        print(f"  Current Period Start: {sub.current_period_start}")
        print(f"  Current Period End: {sub.current_period_end}")

        # Fetch latest invoice for this subscription
        print(f"\n  Fetching latest invoice from Stripe...")
        try:
            invoices_response = await stripe.get(
                f"/invoices?subscription={sub.subscription_id}&limit=1"
            )
            invoices = invoices_response.get("data", [])

            if not invoices:
                print(f"  ❌ No invoices found")
                continue

            invoice = invoices[0]
            print(f"  ✓ Found invoice: {invoice['id']}")

            # Extract period from invoice
            period = extract_invoice_period(invoice)

            if period.start or period.end:
                sub.current_period_start = period.start or sub.current_period_start
                sub.current_period_end = period.end or sub.current_period_end

                repo.upsert(sub)

                print(f"  ✓ Updated billing period:")
                print(f"    Start: {sub.current_period_start}")
                print(f"    End: {sub.current_period_end}")
            else:
                print(f"  ❌ No period data in invoice")

        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
