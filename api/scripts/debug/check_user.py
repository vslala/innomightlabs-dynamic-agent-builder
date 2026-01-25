#!/usr/bin/env python3
"""
Check user details from database.

Usage:
    python scripts/debug/check_user.py testuser@example.com
    python scripts/debug/check_user.py --all
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.users.repository import UserRepository
from src.db import get_dynamodb_resource
from src.config import settings


def check_user(email: str):
    """Check if user exists and display details."""
    repo = UserRepository()

    print(f"Checking user: {email}")
    print("=" * 60)

    user = repo.get_by_email(email)

    if user:
        print("✓ User found:")
        print(f"  Email: {user.email}")
        print(f"  Name: {user.name}")
        print(f"  Stripe Customer ID: {user.stripe_customer_id or 'None'}")
        print(f"  Status: {user.status}")
        print(f"  Picture: {user.picture or 'None'}")
        print(f"  Created: {user.created_at}")
        print(f"  Updated: {user.updated_at}")
        if user.ttl:
            print(f"  TTL (expires): {user.ttl}")
        if user.deletion_requested_at:
            print(f"  Deletion Requested: {user.deletion_requested_at}")
        return True
    else:
        print("❌ User not found")
        return False


def list_all_users():
    """List all users in the database."""
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(settings.dynamodb_table)

    print(f"Listing all users from: {settings.dynamodb_table}")
    if settings.dynamodb_endpoint:
        print(f"Endpoint: {settings.dynamodb_endpoint}")
    print("=" * 60)

    response = table.scan(
        FilterExpression="begins_with(pk, :pk_prefix) AND begins_with(sk, :sk_prefix)",
        ExpressionAttributeValues={
            ":pk_prefix": "USER#",
            ":sk_prefix": "USER#"
        }
    )

    users = response.get("Items", [])
    if users:
        print(f"Found {len(users)} users:\n")
        for user in sorted(users, key=lambda u: u.get("created_at", "")):
            email = user.get("email", "Unknown")
            name = user.get("name", "Unknown")
            created = user.get("created_at", "Unknown")
            stripe_id = user.get("stripe_customer_id", "")
            status = user.get("status", "active")

            print(f"  • {email}")
            print(f"    Name: {name}")
            print(f"    Status: {status}")
            print(f"    Created: {created}")
            if stripe_id:
                print(f"    Stripe: {stripe_id}")
            print()
    else:
        print("No users found")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/debug/check_user.py <email>     # Check specific user")
        print("  python scripts/debug/check_user.py --all       # List all users")
        sys.exit(1)

    if sys.argv[1] == "--all":
        list_all_users()
    else:
        email = sys.argv[1]
        check_user(email)


if __name__ == "__main__":
    main()
