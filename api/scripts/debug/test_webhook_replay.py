#!/usr/bin/env python3
"""
Test webhook handler by replaying a saved webhook event.

Usage:
    python scripts/debug/test_webhook_replay.py /tmp/webhook_events.dat
"""

import sys
import re
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def extract_events_from_log(log_file: str):
    """Extract webhook event JSON from log file."""
    with open(log_file, 'r') as f:
        content = f.read()

    # Find lines that start with b'{ (webhook payloads)
    events = []
    for line in content.split('\n'):
        if line.startswith("b'{"):
            # Extract JSON from byte string format
            json_str = line[2:-1]  # Remove b' and trailing '
            # Unescape
            json_str = json_str.replace('\\n', '\n').replace('\\"', '"')
            try:
                event = json.loads(json_str)
                events.append(event)
            except json.JSONDecodeError:
                pass

    return events


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_webhook_replay.py <log_file>")
        sys.exit(1)

    log_file = sys.argv[1]

    print(f"Extracting events from: {log_file}")
    print("=" * 60)

    events = extract_events_from_log(log_file)

    print(f"Found {len(events)} webhook events")
    print()

    # Group by type
    by_type = {}
    for event in events:
        event_type = event.get('type', 'unknown')
        if event_type not in by_type:
            by_type[event_type] = []
        by_type[event_type].append(event)

    # Show summary
    print("Event types:")
    for event_type, event_list in sorted(by_type.items()):
        print(f"  {len(event_list):2d}  {event_type}")

    print()

    # Show critical events
    print("Critical events for subscription creation:")
    print("-" * 60)

    for event_type in ['invoice.paid', 'invoice.payment_succeeded', 'customer.subscription.created']:
        if event_type in by_type:
            for event in by_type[event_type]:
                event_id = event.get('id', 'unknown')
                data = event.get('data', {}).get('object', {})

                print(f"\n{event_type} (ID: {event_id})")

                if 'subscription' in data:
                    print(f"  Subscription ID: {data.get('subscription')}")
                if 'customer' in data:
                    print(f"  Customer ID: {data.get('customer')}")

                # For subscription events, show details
                if event_type == 'customer.subscription.created':
                    print(f"  Status: {data.get('status')}")
                    metadata = data.get('metadata', {})
                    print(f"  Metadata: {metadata}")

                # For invoice events, show subscription reference
                if event_type in ['invoice.paid', 'invoice.payment_succeeded']:
                    print(f"  Amount: {data.get('amount_paid')}")
                    lines = data.get('lines', {}).get('data', [])
                    if lines:
                        period = lines[0].get('period', {})
                        print(f"  Period: {period.get('start')} - {period.get('end')}")


if __name__ == "__main__":
    main()
