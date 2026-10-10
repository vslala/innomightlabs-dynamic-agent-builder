"""
Lambda handler for cascade deletion of user account data.

Deletion order (child entities first):
1. Messages (by conversation)
2. Conversations
3. Archival Memory → Core Memory → Memory Block Defs (by agent)
4. Crawl Steps → Crawled Pages → Crawl Jobs (by KB)
5. Content Chunks (by KB)
6. Agent-KB Links
7. Knowledge Bases
8. Agents
9. API Keys
10. Provider Settings
11. Subscriptions
12. Usage Records (monthly + active + events)
13. Email Events
14. Identity (with its refresh tokens) and its email index entry

Lambda Configuration:
- Timeout: 900 seconds (15 minutes)
- Memory: 512 MB
- Permissions: DynamoDB read/write
"""

import logging
import os
from typing import Dict, List

import boto3
from boto3.dynamodb.conditions import Key

from src.accounts.models import personal_account_id
from src.accounts.owner import member_partition
from src.identity.models import email_index_key

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class AccountDeletionHandler:
    def __init__(self):
        kwargs = {"region_name": os.getenv("AWS_REGION", "eu-west-2")}
        endpoint = os.getenv("DYNAMODB_ENDPOINT")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        dynamodb = boto3.resource("dynamodb", **kwargs)
        self.table = dynamodb.Table(os.getenv("DYNAMODB_TABLE", ""))

    def delete_user_entities(self, user_id: str, user_email: str) -> Dict[str, int]:
        """Resources are still keyed by the owner's email until they move into accounts (KAN-80)."""
        log.info(f"Starting account deletion for {user_email}")
        counts = {}

        # 1. Delete Messages (by conversation), in the personal account until KAN-83 handles every account
        conversations = member_partition(personal_account_id(user_id), user_id)
        counts["messages"] = self._delete_messages_for_user(conversations)

        # 2. Delete Conversations
        counts["conversations"] = self._delete_items_by_pattern(conversations, "CONVERSATION#")

        # 3. Delete Agents and related data
        agent_ids = self._owned_in_personal_account(user_id, "Agent#", "agent_id")
        counts["archival_memory"] = self._delete_archival_memory_for_agents(agent_ids)
        counts["core_memory"] = self._delete_items_by_agents(agent_ids, "CoreMemory#")
        counts["memory_block_defs"] = self._delete_items_by_agents(agent_ids, "MemoryBlockDef#")
        counts["capacity_warnings"] = self._delete_items_by_agents(agent_ids, "CapacityWarning#")
        counts["widget_conversations"] = self._delete_items_by_agents(agent_ids, "WidgetConversation#")

        # 4. Delete Knowledge Bases and related data (in the personal account, as for agents)
        kb_ids = self._owned_in_personal_account(user_id, "KnowledgeBase#", "kb_id")
        counts["crawl_steps"] = self._delete_crawl_steps_for_kbs(kb_ids)
        counts["crawled_pages"] = self._delete_crawled_pages_for_kbs(kb_ids)
        counts["crawl_jobs"] = self._delete_items_by_kbs(kb_ids, "CrawlJob#")
        counts["content_chunks"] = self._delete_items_by_kbs(kb_ids, "Chunk#")
        counts["content_uploads"] = self._delete_items_by_kbs(kb_ids, "Upload#")

        # 5. Delete Agent-KB Links
        counts["agent_kb_links"] = self._delete_agent_kb_links(agent_ids)

        # 6. Delete Knowledge Bases
        counts["knowledge_bases"] = self._delete_in_personal_account(user_id, "KnowledgeBase#", kb_ids)

        # 7. Delete Agents (in the personal account until KAN-83 handles every account)
        counts["agents"] = self._delete_in_personal_account(user_id, "Agent#", agent_ids)

        # 8. Delete API Keys
        counts["api_keys"] = self._delete_items_by_pattern(
            f"User#{user_email}", "ApiKey#"
        )

        # 9. Delete Provider Settings
        counts["provider_settings"] = self._delete_items_by_pattern(
            f"User#{user_email}", "ProviderSettings#"
        )

        # 9b. Delete refresh tokens issued to other apps that share this login
        counts["refresh_tokens"] = self._delete_items_by_pattern(
            f"Identity#{user_id}", "RefreshToken#"
        )

        # 10. Delete Subscriptions
        counts["subscriptions"] = self._delete_items_by_pattern(
            f"User#{user_email}", "Subscription#"
        )

        # 11. Delete Usage Records
        counts["usage_monthly"] = self._delete_items_by_pattern(
            f"Usage#{user_email}", "Month#"
        )
        counts["usage_active"] = self._delete_items_by_pattern(
            f"Usage#{user_email}", "Active#"
        )
        counts["usage_events"] = self._delete_items_by_pattern(
            f"UsageEvent#{user_email}", ""
        )

        # 12. Delete Email Events
        counts["email_events"] = self._delete_items_by_pattern(
            f"EmailEvent#{user_email}", ""
        )

        # 13. Delete the identity and free its email
        counts["identity"] = self._delete_identity(user_id, user_email)

        log.info(f"Completed account deletion for {user_email}: {counts}")
        return counts

    def _delete_items_by_pattern(self, pk: str, sk_prefix: str) -> int:
        count = 0
        try:
            last_evaluated_key = None
            while True:
                query_params = {
                    "KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)
                }
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key

                response = self.table.query(**query_params)
                items = response.get("Items", [])

                if items:
                    with self.table.batch_writer() as batch:
                        for item in items:
                            batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                            count += 1

                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            log.info(f"Deleted {count} items with pk={pk}, sk_prefix={sk_prefix}")
        except Exception as e:
            log.error(f"Error deleting items pk={pk}, sk_prefix={sk_prefix}: {e}")

        return count

    def _owned_in_personal_account(self, user_id: str, sk_prefix: str, id_field: str) -> List[str]:
        """Ids of what the person owns of one type in their personal account. Leaving shared accounts, and
        what they own there, comes with offboarding (KAN-83)."""
        ids: List[str] = []
        query_params = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{personal_account_id(user_id)}")
            & Key("sk").begins_with(sk_prefix),
        }
        try:
            while True:
                response = self.table.query(**query_params)
                ids += [item[id_field] for item in response.get("Items", []) if item.get("owner_id") == user_id]
                if "LastEvaluatedKey" not in response:
                    break
                query_params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            log.info(f"Found {len(ids)} {sk_prefix} items for {user_id}")
        except Exception as e:
            log.error(f"Error getting {sk_prefix} ids for {user_id}: {e}")
        return ids

    def _delete_in_personal_account(self, user_id: str, sk_prefix: str, ids: List[str]) -> int:
        pk = f"Account#{personal_account_id(user_id)}"
        with self.table.batch_writer() as batch:
            for item_id in ids:
                batch.delete_item(Key={"pk": pk, "sk": f"{sk_prefix}{item_id}"})
        return len(ids)

    def _delete_items_by_agents(self, agent_ids: List[str], sk_prefix: str) -> int:
        count = 0
        for agent_id in agent_ids:
            count += self._delete_items_by_pattern(f"Agent#{agent_id}", sk_prefix)
        return count

    def _delete_archival_memory_for_agents(self, agent_ids: List[str]) -> int:
        count = 0
        for agent_id in agent_ids:
            # Delete by primary key pattern
            count += self._delete_items_by_pattern(f"Agent#{agent_id}", "ArchivalMemory#")
            # Also need to query and delete by hash index if exists
            # This would require scanning or using GSI
        return count

    def _delete_agent_kb_links(self, agent_ids: List[str]) -> int:
        count = 0
        for agent_id in agent_ids:
            count += self._delete_items_by_pattern(f"Agent#{agent_id}", "KnowledgeBase#")
        return count

    def _delete_items_by_kbs(self, kb_ids: List[str], sk_prefix: str) -> int:
        count = 0
        for kb_id in kb_ids:
            count += self._delete_items_by_pattern(f"KnowledgeBase#{kb_id}", sk_prefix)
        return count

    def _delete_crawl_steps_for_kbs(self, kb_ids: List[str]) -> int:
        count = 0
        for kb_id in kb_ids:
            # Get all crawl jobs for this KB
            crawl_job_ids = []
            try:
                last_evaluated_key = None
                while True:
                    query_params = {
                        "KeyConditionExpression": Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("CrawlJob#")
                    }
                    if last_evaluated_key:
                        query_params["ExclusiveStartKey"] = last_evaluated_key

                    response = self.table.query(**query_params)
                    items = response.get("Items", [])

                    for item in items:
                        sk = item.get("sk", "")
                        if sk.startswith("CrawlJob#"):
                            job_id = sk.replace("CrawlJob#", "")
                            crawl_job_ids.append(job_id)

                    last_evaluated_key = response.get("LastEvaluatedKey")
                    if not last_evaluated_key:
                        break
            except Exception as e:
                log.error(f"Error getting crawl job IDs for KB {kb_id}: {e}")

            # Delete steps for each job
            for job_id in crawl_job_ids:
                count += self._delete_items_by_pattern(f"CrawlJob#{job_id}", "Step#")

        return count

    def _delete_crawled_pages_for_kbs(self, kb_ids: List[str]) -> int:
        count = 0
        for kb_id in kb_ids:
            # Get all crawl jobs for this KB
            crawl_job_ids = []
            try:
                last_evaluated_key = None
                while True:
                    query_params = {
                        "KeyConditionExpression": Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("CrawlJob#")
                    }
                    if last_evaluated_key:
                        query_params["ExclusiveStartKey"] = last_evaluated_key

                    response = self.table.query(**query_params)
                    items = response.get("Items", [])

                    for item in items:
                        sk = item.get("sk", "")
                        if sk.startswith("CrawlJob#"):
                            job_id = sk.replace("CrawlJob#", "")
                            crawl_job_ids.append(job_id)

                    last_evaluated_key = response.get("LastEvaluatedKey")
                    if not last_evaluated_key:
                        break
            except Exception as e:
                log.error(f"Error getting crawl job IDs for KB {kb_id}: {e}")

            # Delete pages for each job
            for job_id in crawl_job_ids:
                count += self._delete_items_by_pattern(f"CrawlJob#{job_id}", "Page#")

        return count

    def _delete_messages_for_user(self, partition: str) -> int:
        count = 0
        # Get all conversation IDs for the user
        conversation_ids = []
        try:
            last_evaluated_key = None
            while True:
                query_params = {
                    "KeyConditionExpression": Key("pk").eq(partition) & Key("sk").begins_with("CONVERSATION#")
                }
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key

                response = self.table.query(**query_params)
                items = response.get("Items", [])

                for item in items:
                    sk = item.get("sk", "")
                    if sk.startswith("CONVERSATION#"):
                        conv_id = sk.replace("CONVERSATION#", "")
                        conversation_ids.append(conv_id)

                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break
        except Exception as e:
            log.error(f"Error getting conversation IDs in {partition}: {e}")

        # Delete each conversation's partition: messages, tool audit and turns
        for conv_id in conversation_ids:
            count += self._delete_items_by_pattern(f"CONVERSATION#{conv_id}", "")

        return count

    def _delete_identity(self, user_id: str, user_email: str) -> int:
        try:
            self.table.delete_item(Key={"pk": f"Identity#{user_id}", "sk": "Identity#Metadata"})
            self.table.delete_item(
                Key=email_index_key(user_email),
                ConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
            )
            log.info(f"Deleted identity {user_id} ({user_email})")
            return 1
        except Exception as e:
            log.error(f"Error deleting identity {user_id} ({user_email}): {e}")
            return 0


def handler(event, context):
    """
    Lambda handler for account deletion.

    Expected event format:
    {
        "user_id": "3f0c…",
        "user_email": "user@example.com"
    }
    """
    user_id = event.get("user_id")
    user_email = event.get("user_email")

    if not user_id or not user_email:
        log.error(f"Invalid event payload: {event}")
        return {
            "statusCode": 400,
            "body": "Missing user_id or user_email in event payload"
        }

    deletion_handler = AccountDeletionHandler()
    counts = deletion_handler.delete_user_entities(user_id, user_email)

    return {
        "statusCode": 200,
        "body": f"Account deletion completed for {user_email}",
        "counts": counts
    }
