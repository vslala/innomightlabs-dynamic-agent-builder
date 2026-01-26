#!/usr/bin/env python3
"""
Complete user account deletion script.

This script deletes ALL data associated with a user account following the entity hierarchy:
- User record
- Conversations and Messages
- Agents and all related data (memory, API keys, widget conversations)
- Knowledge Bases and all related data (chunks, crawl jobs, steps, pages)
- Provider Settings
- Subscriptions
- Usage Records
- Email Events

Usage:
    # Dry run (shows what would be deleted without actually deleting)
    python scripts/delete_user_account.py user@example.com --dry-run

    # Actually delete (requires confirmation)
    python scripts/delete_user_account.py user@example.com

    # Skip confirmation prompt (dangerous!)
    python scripts/delete_user_account.py user@example.com --yes

Environment Variables:
    DYNAMODB_ENDPOINT - Optional local DynamoDB endpoint (e.g., http://localhost:8001)
    DYNAMODB_TABLE - DynamoDB table name (default: dynamic-agent-builder-main)
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db import get_dynamodb_resource
from src.config import settings


class UserAccountDeleter:
    """Handles complete deletion of user account data."""

    def __init__(self, email: str, dry_run: bool = False):
        self.email = email
        self.dry_run = dry_run
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)
        self.deletion_stats = defaultdict(int)
        self.items_to_delete: List[Dict[str, Any]] = []

    def scan_user_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Scan and categorize all data related to the user."""
        print(f"\n{'🔍' if not self.dry_run else '🔎'} Scanning for data associated with: {self.email}")
        print("=" * 80)

        all_data = {
            "user": [],
            "conversations": [],
            "messages": [],
            "agents": [],
            "agent_memory": [],
            "agent_archival": [],
            "agent_capacity": [],
            "api_keys": [],
            "widget_conversations": [],
            "agent_kb_links": [],
            "knowledge_bases": [],
            "content_chunks": [],
            "crawl_jobs": [],
            "crawl_steps": [],
            "crawled_pages": [],
            "provider_settings": [],
            "subscriptions": [],
            "usage_records": [],
            "email_events": [],
            "webhook_events": [],
        }

        # 1. Find User record
        print(f"  • Scanning User record...")
        user_items = self._query_items(f"User#{self.email}")
        all_data["user"].extend(user_items)

        # 2. Find Conversations
        print(f"  • Scanning Conversations...")
        conversation_items = self._query_items(f"User#{self.email}", sk_prefix="CONVERSATION#")
        all_data["conversations"].extend(conversation_items)

        # Get conversation IDs for message queries
        conversation_ids = [item["sk"].replace("CONVERSATION#", "") for item in conversation_items]

        # 3. Find Messages for each conversation
        print(f"  • Scanning Messages ({len(conversation_ids)} conversations)...")
        for conv_id in conversation_ids:
            message_items = self._query_items(f"CONVERSATION#{conv_id}", sk_prefix="MESSAGE#")
            all_data["messages"].extend(message_items)

        # 4. Find Agents
        print(f"  • Scanning Agents...")
        agent_items = self._query_items(f"User#{self.email}", sk_prefix="AGENT#")
        all_data["agents"].extend(agent_items)

        # Get agent IDs for related data queries
        agent_ids = [item["sk"].replace("AGENT#", "") for item in agent_items]

        # 5. Find Agent-related data
        if agent_ids:
            print(f"  • Scanning Agent-related data ({len(agent_ids)} agents)...")
            for agent_id in agent_ids:
                # Memory block definitions
                memory_items = self._query_items(f"AGENT#{agent_id}", sk_prefix="MEMORY#")
                all_data["agent_memory"].extend(memory_items)

                # Archival memory
                archival_items = self._query_items(f"AGENT#{agent_id}", sk_prefix="ARCHIVAL#")
                all_data["agent_archival"].extend(archival_items)

                # Capacity warnings
                capacity_items = self._query_items(f"AGENT#{agent_id}", sk_prefix="CAPACITY#")
                all_data["agent_capacity"].extend(capacity_items)

                # API Keys (GSI2: AGENT#{agent_id} → APIKEY#*)
                api_key_items = self._query_gsi2(f"AGENT#{agent_id}", sk_prefix="APIKEY#")
                all_data["api_keys"].extend(api_key_items)

                # Widget Conversations (GSI2: AGENT#{agent_id} → WIDGET_CONVERSATION#*)
                widget_items = self._query_gsi2(f"AGENT#{agent_id}", sk_prefix="WIDGET_CONVERSATION#")
                all_data["widget_conversations"].extend(widget_items)

                # Agent-KnowledgeBase links
                kb_link_items = self._query_items(f"AGENT#{agent_id}", sk_prefix="KB#")
                all_data["agent_kb_links"].extend(kb_link_items)

        # 6. Find Knowledge Bases
        print(f"  • Scanning Knowledge Bases...")
        kb_items = self._query_items(f"User#{self.email}", sk_prefix="KB#")
        all_data["knowledge_bases"].extend(kb_items)

        # Get KB IDs for related data queries
        kb_ids = [item["sk"].replace("KB#", "") for item in kb_items]

        # 7. Find KB-related data
        if kb_ids:
            print(f"  • Scanning KB-related data ({len(kb_ids)} knowledge bases)...")
            for kb_id in kb_ids:
                # Content chunks
                chunk_items = self._query_items(f"KB#{kb_id}", sk_prefix="CHUNK#")
                all_data["content_chunks"].extend(chunk_items)

                # Crawl jobs
                job_items = self._query_items(f"KB#{kb_id}", sk_prefix="CRAWL_JOB#")
                all_data["crawl_jobs"].extend(job_items)

                # Get job IDs for steps and pages
                job_ids = [item["sk"].replace("CRAWL_JOB#", "") for item in job_items]

                for job_id in job_ids:
                    # Crawl steps
                    step_items = self._query_items(f"CRAWL_JOB#{job_id}", sk_prefix="STEP#")
                    all_data["crawl_steps"].extend(step_items)

                    # Crawled pages
                    page_items = self._query_items(f"CRAWL_JOB#{job_id}", sk_prefix="PAGE#")
                    all_data["crawled_pages"].extend(page_items)

        # 8. Find Provider Settings
        print(f"  • Scanning Provider Settings...")
        provider_items = self._query_items(f"User#{self.email}", sk_prefix="PROVIDER#")
        all_data["provider_settings"].extend(provider_items)

        # 9. Find Subscriptions
        print(f"  • Scanning Subscriptions...")
        subscription_items = self._query_items(f"User#{self.email}", sk_prefix="SUBSCRIPTION#")
        all_data["subscriptions"].extend(subscription_items)

        # 10. Find Usage Records
        print(f"  • Scanning Usage Records...")
        usage_items = self._query_items(f"User#{self.email}", sk_prefix="USAGE#")
        all_data["usage_records"].extend(usage_items)

        # Also check for active usage counter
        active_usage = self._query_items(f"User#{self.email}", sk_prefix="ACTIVE_USAGE")
        all_data["usage_records"].extend(active_usage)

        # 11. Find Email Events
        print(f"  • Scanning Email Events...")
        email_items = self._query_items(f"User#{self.email}", sk_prefix="EMAIL_EVENT#")
        all_data["email_events"].extend(email_items)

        # 12. Find Webhook Events (if any tied to user)
        print(f"  • Scanning Webhook Events...")
        webhook_items = self._query_items(f"User#{self.email}", sk_prefix="WEBHOOK_EVENT#")
        all_data["webhook_events"].extend(webhook_items)

        return all_data

    def _query_items(self, pk: str, sk_prefix: str = None) -> List[Dict[str, Any]]:
        """Query items by PK and optional SK prefix."""
        try:
            if sk_prefix:
                response = self.table.query(
                    KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
                    ExpressionAttributeValues={
                        ":pk": pk,
                        ":sk_prefix": sk_prefix,
                    },
                )
            else:
                response = self.table.query(
                    KeyConditionExpression="pk = :pk",
                    ExpressionAttributeValues={":pk": pk},
                )
            return response.get("Items", [])
        except Exception as e:
            print(f"    ⚠️  Error querying {pk} / {sk_prefix}: {e}")
            return []

    def _query_gsi2(self, gsi2pk: str, sk_prefix: str = None) -> List[Dict[str, Any]]:
        """Query items using GSI2 (gsi2pk, gsi2sk)."""
        try:
            if sk_prefix:
                response = self.table.query(
                    IndexName="gsi2",
                    KeyConditionExpression="gsi2pk = :gsi2pk AND begins_with(gsi2sk, :sk_prefix)",
                    ExpressionAttributeValues={
                        ":gsi2pk": gsi2pk,
                        ":sk_prefix": sk_prefix,
                    },
                )
            else:
                response = self.table.query(
                    IndexName="gsi2",
                    KeyConditionExpression="gsi2pk = :gsi2pk",
                    ExpressionAttributeValues={":gsi2pk": gsi2pk},
                )
            return response.get("Items", [])
        except Exception as e:
            print(f"    ⚠️  Error querying GSI2 {gsi2pk} / {sk_prefix}: {e}")
            return []

    def display_summary(self, all_data: Dict[str, List[Dict[str, Any]]]) -> int:
        """Display summary of data to be deleted."""
        print("\n" + "=" * 80)
        print(f"📊 DELETION SUMMARY for {self.email}")
        print("=" * 80)

        total_items = 0
        for category, items in all_data.items():
            if items:
                count = len(items)
                total_items += count
                category_name = category.replace("_", " ").title()
                print(f"  • {category_name:.<40} {count:>6} items")

        print("=" * 80)
        print(f"  {'TOTAL ITEMS TO DELETE':.<40} {total_items:>6}")
        print("=" * 80)

        return total_items

    def delete_all_data(self, all_data: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Delete all data in the correct order."""
        if self.dry_run:
            print(f"\n🔎 DRY RUN - No data will be deleted")
            return True

        print(f"\n🗑️  DELETING DATA (This cannot be undone!)")
        print("=" * 80)

        # Deletion order: children first, then parents
        deletion_order = [
            ("crawled_pages", "Crawled Pages"),
            ("crawl_steps", "Crawl Steps"),
            ("crawl_jobs", "Crawl Jobs"),
            ("content_chunks", "Content Chunks"),
            ("knowledge_bases", "Knowledge Bases"),
            ("widget_conversations", "Widget Conversations"),
            ("api_keys", "API Keys"),
            ("agent_kb_links", "Agent-KB Links"),
            ("agent_capacity", "Agent Capacity Warnings"),
            ("agent_archival", "Agent Archival Memory"),
            ("agent_memory", "Agent Memory"),
            ("agents", "Agents"),
            ("messages", "Messages"),
            ("conversations", "Conversations"),
            ("webhook_events", "Webhook Events"),
            ("email_events", "Email Events"),
            ("usage_records", "Usage Records"),
            ("subscriptions", "Subscriptions"),
            ("provider_settings", "Provider Settings"),
            ("user", "User Record"),
        ]

        for category, display_name in deletion_order:
            items = all_data.get(category, [])
            if items:
                print(f"\n  Deleting {display_name}... ({len(items)} items)")
                self._batch_delete_items(items, display_name)

        print("\n" + "=" * 80)
        print(f"✅ DELETION COMPLETE")
        print("=" * 80)
        print(f"\nDeleted {sum(self.deletion_stats.values())} total items")
        return True

    def _batch_delete_items(self, items: List[Dict[str, Any]], category: str):
        """Delete items in batches of 25 (DynamoDB limit)."""
        batch_size = 25
        total = len(items)
        deleted = 0

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]

            try:
                with self.table.batch_writer() as writer:
                    for item in batch:
                        writer.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                        deleted += 1

                print(f"    ✓ Deleted {deleted}/{total} {category}")

            except Exception as e:
                print(f"    ✗ Error deleting batch: {e}")

        self.deletion_stats[category] = deleted


def confirm_deletion(email: str) -> bool:
    """Ask user to confirm deletion."""
    print("\n" + "=" * 80)
    print("⚠️  WARNING: THIS ACTION CANNOT BE UNDONE!")
    print("=" * 80)
    print(f"\nYou are about to permanently delete ALL data for: {email}")
    print("\nThis includes:")
    print("  • User account")
    print("  • All conversations and messages")
    print("  • All agents and their memory")
    print("  • All knowledge bases and content")
    print("  • All subscriptions and usage records")
    print("  • Everything else associated with this account")
    print("\n" + "=" * 80)

    response = input(f'\nType "{email}" to confirm deletion: ')
    return response == email


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Delete all data associated with a user account",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("email", help="Email address of the user to delete")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt (dangerous!)",
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print(f"🗑️  USER ACCOUNT DELETION TOOL")
    print("=" * 80)
    print(f"\nTarget User: {args.email}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE DELETION'}")
    print(f"Database: {settings.dynamodb_table}")
    if settings.dynamodb_endpoint:
        print(f"Endpoint: {settings.dynamodb_endpoint}")

    # Initialize deleter
    deleter = UserAccountDeleter(args.email, dry_run=args.dry_run)

    # Scan for all user data
    all_data = deleter.scan_user_data()

    # Display summary
    total_items = deleter.display_summary(all_data)

    if total_items == 0:
        print(f"\n✓ No data found for {args.email}")
        return 0

    # Confirm deletion
    if not args.dry_run:
        if not args.yes:
            if not confirm_deletion(args.email):
                print("\n❌ Deletion cancelled by user")
                return 1

        # Delete all data
        deleter.delete_all_data(all_data)
    else:
        print(f"\n🔎 DRY RUN COMPLETE - No data was deleted")
        print(f"   Run without --dry-run to actually delete this data")

    return 0


if __name__ == "__main__":
    sys.exit(main())
