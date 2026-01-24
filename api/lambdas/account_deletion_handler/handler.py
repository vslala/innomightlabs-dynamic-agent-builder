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
14. User record

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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class AccountDeletionHandler:
    def __init__(self):
        dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "eu-west-2"))
        self.table = dynamodb.Table(os.getenv("DYNAMODB_TABLE", ""))

    def delete_user_entities(self, user_email: str) -> Dict[str, int]:
        log.info(f"Starting account deletion for {user_email}")
        counts = {}

        # 1. Delete Messages (by conversation)
        counts["messages"] = self._delete_messages_for_user(user_email)

        # 2. Delete Conversations
        counts["conversations"] = self._delete_items_by_pattern(
            f"USER#{user_email}", "CONVERSATION#"
        )

        # 3. Delete Agents and related data
        agent_ids = self._get_agent_ids_for_user(user_email)
        counts["archival_memory"] = self._delete_archival_memory_for_agents(agent_ids)
        counts["core_memory"] = self._delete_items_by_agents(agent_ids, "CoreMemory#")
        counts["memory_block_defs"] = self._delete_items_by_agents(agent_ids, "MemoryBlockDef#")
        counts["capacity_warnings"] = self._delete_items_by_agents(agent_ids, "CapacityWarning#")
        counts["widget_conversations"] = self._delete_items_by_agents(agent_ids, "WidgetConversation#")

        # 4. Delete Knowledge Bases and related data
        kb_ids = self._get_kb_ids_for_user(user_email)
        counts["crawl_steps"] = self._delete_crawl_steps_for_kbs(kb_ids, user_email)
        counts["crawled_pages"] = self._delete_crawled_pages_for_kbs(kb_ids, user_email)
        counts["crawl_jobs"] = self._delete_items_by_kbs(kb_ids, user_email, "CrawlJob#")
        counts["content_chunks"] = self._delete_items_by_kbs(kb_ids, user_email, "ContentChunk#")

        # 5. Delete Agent-KB Links
        counts["agent_kb_links"] = self._delete_agent_kb_links(agent_ids)

        # 6. Delete Knowledge Bases
        counts["knowledge_bases"] = self._delete_items_by_pattern(
            f"User#{user_email}", "KnowledgeBase#"
        )

        # 7. Delete Agents
        counts["agents"] = self._delete_items_by_pattern(
            f"User#{user_email}", "Agent#"
        )

        # 8. Delete API Keys
        counts["api_keys"] = self._delete_items_by_pattern(
            f"User#{user_email}", "ApiKey#"
        )

        # 9. Delete Provider Settings
        counts["provider_settings"] = self._delete_items_by_pattern(
            f"User#{user_email}", "ProviderSettings#"
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

        # 13. Delete User record
        counts["user"] = self._delete_user_record(user_email)

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

    def _get_agent_ids_for_user(self, user_email: str) -> List[str]:
        agent_ids = []
        try:
            last_evaluated_key = None
            while True:
                query_params = {
                    "KeyConditionExpression": Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with("Agent#")
                }
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key

                response = self.table.query(**query_params)
                items = response.get("Items", [])

                for item in items:
                    sk = item.get("sk", "")
                    if sk.startswith("Agent#"):
                        agent_id = sk.replace("Agent#", "")
                        agent_ids.append(agent_id)

                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            log.info(f"Found {len(agent_ids)} agents for {user_email}")
        except Exception as e:
            log.error(f"Error getting agent IDs for {user_email}: {e}")

        return agent_ids

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
            count += self._delete_items_by_pattern(f"Agent#{agent_id}", "AgentKnowledgeBase#")
        return count

    def _get_kb_ids_for_user(self, user_email: str) -> List[str]:
        kb_ids = []
        try:
            last_evaluated_key = None
            while True:
                query_params = {
                    "KeyConditionExpression": Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with("KnowledgeBase#")
                }
                if last_evaluated_key:
                    query_params["ExclusiveStartKey"] = last_evaluated_key

                response = self.table.query(**query_params)
                items = response.get("Items", [])

                for item in items:
                    sk = item.get("sk", "")
                    if sk.startswith("KnowledgeBase#"):
                        kb_id = sk.replace("KnowledgeBase#", "")
                        kb_ids.append(kb_id)

                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            log.info(f"Found {len(kb_ids)} knowledge bases for {user_email}")
        except Exception as e:
            log.error(f"Error getting KB IDs for {user_email}: {e}")

        return kb_ids

    def _delete_items_by_kbs(self, kb_ids: List[str], user_email: str, sk_prefix: str) -> int:
        count = 0
        for kb_id in kb_ids:
            count += self._delete_items_by_pattern(f"KnowledgeBase#{kb_id}", sk_prefix)
        return count

    def _delete_crawl_steps_for_kbs(self, kb_ids: List[str], user_email: str) -> int:
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
                count += self._delete_items_by_pattern(f"CrawlJob#{job_id}", "CrawlStep#")

        return count

    def _delete_crawled_pages_for_kbs(self, kb_ids: List[str], user_email: str) -> int:
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
                count += self._delete_items_by_pattern(f"CrawlJob#{job_id}", "CrawledPage#")

        return count

    def _delete_messages_for_user(self, user_email: str) -> int:
        count = 0
        # Get all conversation IDs for the user
        conversation_ids = []
        try:
            last_evaluated_key = None
            while True:
                query_params = {
                    "KeyConditionExpression": Key("pk").eq(f"USER#{user_email}") & Key("sk").begins_with("CONVERSATION#")
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
            log.error(f"Error getting conversation IDs for {user_email}: {e}")

        # Delete messages for each conversation
        for conv_id in conversation_ids:
            count += self._delete_items_by_pattern(f"CONVERSATION#{conv_id}", "MESSAGE#")

        return count

    def _delete_user_record(self, user_email: str) -> int:
        try:
            self.table.delete_item(
                Key={
                    "pk": f"User#{user_email}",
                    "sk": "User#Metadata"
                }
            )
            log.info(f"Deleted user record for {user_email}")
            return 1
        except Exception as e:
            log.error(f"Error deleting user record for {user_email}: {e}")
            return 0


def handler(event, context):
    """
    Lambda handler for account deletion.

    Expected event format:
    {
        "user_email": "user@example.com"
    }
    """
    user_email = event.get("user_email")

    if not user_email:
        log.error(f"Invalid event payload: {event}")
        return {
            "statusCode": 400,
            "body": "Missing user_email in event payload"
        }

    deletion_handler = AccountDeletionHandler()
    counts = deletion_handler.delete_user_entities(user_email)

    return {
        "statusCode": 200,
        "body": f"Account deletion completed for {user_email}",
        "counts": counts
    }
