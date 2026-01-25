#!/usr/bin/env python3
"""
Check user details from database.

Usage:
    python scripts/debug/check_user.py testuser@example.com
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.users.repository import UserRepository


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_user.py <email>")
        sys.exit(1)

    email = sys.argv[1]
    repo = UserRepository()

    print(f"Checking user: {email}")
    print("=" * 60)

    user = repo.get_by_email(email)

    if user:
        print("✓ User found:")
        print(f"  Email: {user.email}")
        print(f"  Name: {user.name}")
        print(f"  Stripe Customer ID: {user.stripe_customer_id}")
        print(f"  Status: {user.status}")
        print(f"  Picture: {user.picture}")
        print(f"  Created: {user.created_at}")
        print(f"  Updated: {user.updated_at}")
        if user.ttl:
            print(f"  TTL (expires): {user.ttl}")
        if user.deletion_requested_at:
            print(f"  Deletion Requested: {user.deletion_requested_at}")
    else:
        print("❌ User not found")


if __name__ == "__main__":
    main()
