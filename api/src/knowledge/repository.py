"""
Repository for Knowledge Base, CrawlJob, and related entities.

Uses DynamoDB single table design with the following access patterns:

KnowledgeBase:
    - List all KBs for a user: Query pk=User#{email}, sk begins_with KnowledgeBase#
    - Get KB by ID: GetItem pk=User#{email}, sk=KnowledgeBase#{kb_id}
    - Create/Update KB: PutItem
    - Delete KB (soft): UpdateItem to set status=deleted

CrawlJob:
    - List jobs for KB: Query pk=KnowledgeBase#{kb_id}, sk begins_with CrawlJob#
    - Get job by ID: GetItem pk=KnowledgeBase#{kb_id}, sk=CrawlJob#{job_id}
    - Create/Update job: PutItem

CrawlStep:
    - List steps for job: Query pk=CrawlJob#{job_id}, sk begins_with Step#
    - Create step: PutItem

CrawledPage:
    - List pages for job: Query pk=CrawlJob#{job_id}, sk begins_with Page#
    - Get/Update page: GetItem/PutItem

ContentChunk:
    - Get chunk by ID: GetItem pk=KnowledgeBase#{kb_id}, sk=Chunk#{chunk_id}
    - Create chunks: BatchWriteItem

AgentKnowledgeBase:
    - List KBs for agent: Query pk=Agent#{agent_id}, sk begins_with KnowledgeBase#
    - List agents for KB: Query GSI2 gsi2_pk=KnowledgeBase#{kb_id}
    - Link/Unlink: PutItem/DeleteItem
"""

import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone
from typing import Optional
import logging

from src.config import settings
from src.knowledge.models import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    CrawlJob,
    CrawlStep,
    CrawledPage,
    ContentChunk,
    AgentKnowledgeBase,
)

log = logging.getLogger(__name__)


class KnowledgeBaseRepository:
    """Repository for KnowledgeBase entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, kb: KnowledgeBase) -> KnowledgeBase:
        """Save a knowledge base (create or update)."""
        existing = self.find_by_id(kb.kb_id, kb.created_by)

        if existing:
            kb.created_at = existing.created_at
            kb.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=kb.to_dynamo_item())
        log.info(f"Saved knowledge base {kb.kb_id} for user {kb.created_by}")
        return kb

    def find_by_id(self, kb_id: str, user_email: str) -> Optional[KnowledgeBase]:
        """Find a knowledge base by ID."""
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"KnowledgeBase#{kb_id}",
            }
        )
        item = response.get("Item")
        if item:
            return KnowledgeBase.from_dynamo_item(item)
        return None

    def find_all_by_user(self, user_email: str, include_deleted: bool = False) -> list[KnowledgeBase]:
        """Find all knowledge bases for a user."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{user_email}")
            & Key("sk").begins_with("KnowledgeBase#")
        )

        items = response.get("Items", [])
        kbs = [KnowledgeBase.from_dynamo_item(item) for item in items]

        if not include_deleted:
            kbs = [kb for kb in kbs if kb.status != KnowledgeBaseStatus.DELETED]

        log.info(f"Found {len(kbs)} knowledge bases for user {user_email}")
        return kbs

    def soft_delete(self, kb_id: str, user_email: str) -> bool:
        """Soft delete a knowledge base by setting status to deleted."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"User#{user_email}",
                    "sk": f"KnowledgeBase#{kb_id}",
                },
                UpdateExpression="SET #status = :status, updated_at = :updated_at",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": KnowledgeBaseStatus.DELETED.value,
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            log.info(f"Soft deleted knowledge base {kb_id}")
            return True
        except Exception as e:
            log.error(f"Failed to soft delete knowledge base {kb_id}: {e}", exc_info=True)
            return False

    def update_stats(self, kb_id: str, user_email: str, total_pages: int, total_chunks: int, total_vectors: int) -> bool:
        """Update knowledge base statistics after a crawl."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"User#{user_email}",
                    "sk": f"KnowledgeBase#{kb_id}",
                },
                UpdateExpression="SET total_pages = :pages, total_chunks = :chunks, total_vectors = :vectors, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":pages": total_pages,
                    ":chunks": total_chunks,
                    ":vectors": total_vectors,
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return True
        except Exception as e:
            log.error(f"Failed to update stats for KB {kb_id}: {e}", exc_info=True)
            return False


class CrawlJobRepository:
    """Repository for CrawlJob entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, job: CrawlJob) -> CrawlJob:
        """Save a crawl job."""
        self.table.put_item(Item=job.to_dynamo_item())
        log.info(f"Saved crawl job {job.job_id} for KB {job.kb_id}")
        return job

    def find_by_id(self, job_id: str, kb_id: str) -> Optional[CrawlJob]:
        """Find a crawl job by ID."""
        response = self.table.get_item(
            Key={
                "pk": f"KnowledgeBase#{kb_id}",
                "sk": f"CrawlJob#{job_id}",
            }
        )
        item = response.get("Item")
        if item:
            return CrawlJob.from_dynamo_item(item)
        return None

    def find_all_by_kb(self, kb_id: str, limit: int = 5) -> list[CrawlJob]:
        """Find all crawl jobs for a knowledge base, ordered by creation time (most recent first)."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"KnowledgeBase#{kb_id}")
            & Key("sk").begins_with("CrawlJob#"),
            ScanIndexForward=False,  # Most recent first
            Limit=limit,
        )

        items = response.get("Items", [])
        jobs = [CrawlJob.from_dynamo_item(item) for item in items]

        # Sort by created_at descending (most recent first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        log.info(f"Found {len(jobs)} crawl jobs for KB {kb_id}")
        return jobs[:limit]

    def update_status(self, job_id: str, kb_id: str, status: str, error_message: Optional[str] = None) -> bool:
        """Update crawl job status."""
        try:
            update_expr = "SET #status = :status"
            expr_attr_values = {":status": status}
            expr_attr_names = {"#status": "status"}

            if error_message:
                update_expr += ", error_message = :error"
                expr_attr_values[":error"] = error_message

            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
            )
            return True
        except Exception as e:
            log.error(f"Failed to update job status: {e}", exc_info=True)
            return False

    def update_progress(self, job_id: str, kb_id: str, progress: dict) -> bool:
        """Update crawl job progress."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression="SET progress = :progress",
                ExpressionAttributeValues={":progress": progress},
            )
            return True
        except Exception as e:
            log.error(f"Failed to update job progress: {e}", exc_info=True)
            return False

    def update_checkpoint(self, job_id: str, kb_id: str, checkpoint: dict) -> bool:
        """Update crawl job checkpoint for Lambda continuation."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression="SET checkpoint = :checkpoint",
                ExpressionAttributeValues={":checkpoint": checkpoint},
            )
            return True
        except Exception as e:
            log.error(f"Failed to update checkpoint: {e}", exc_info=True)
            return False

    def update_timing(self, job_id: str, kb_id: str, timing: dict) -> bool:
        """Update crawl job timing information."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression="SET timing = :timing",
                ExpressionAttributeValues={":timing": timing},
            )
            return True
        except Exception as e:
            log.error(f"Failed to update timing: {e}", exc_info=True)
            return False


class CrawlStepRepository:
    """Repository for CrawlStep (audit log) entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, step: CrawlStep) -> CrawlStep:
        """Save a crawl step."""
        self.table.put_item(Item=step.to_dynamo_item())
        return step

    def find_all_by_job(
        self, job_id: str, limit: int = 100, last_evaluated_key: Optional[dict] = None
    ) -> tuple[list[CrawlStep], Optional[dict]]:
        """Find all steps for a crawl job with pagination."""
        query_params = {
            "KeyConditionExpression": Key("pk").eq(f"CrawlJob#{job_id}")
            & Key("sk").begins_with("Step#"),
            "Limit": limit,
        }

        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        steps = [CrawlStep.from_dynamo_item(item) for item in items]
        next_key = response.get("LastEvaluatedKey")

        return steps, next_key

    def find_steps_after_cursor(
        self, job_id: str, cursor_sk: Optional[str] = None, limit: int = 50
    ) -> tuple[list[CrawlStep], Optional[str]]:
        """
        Find steps after a given cursor (sort key) for polling.
        Returns steps and the last step's sk as the new cursor.
        """
        query_params = {
            "KeyConditionExpression": Key("pk").eq(f"CrawlJob#{job_id}")
            & Key("sk").begins_with("Step#"),
            "Limit": limit,
            "ScanIndexForward": True,
        }

        if cursor_sk:
            query_params["ExclusiveStartKey"] = {
                "pk": f"CrawlJob#{job_id}",
                "sk": cursor_sk,
            }

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        steps = [CrawlStep.from_dynamo_item(item) for item in items]

        new_cursor = None
        if steps:
            new_cursor = items[-1]["sk"]

        return steps, new_cursor


class CrawledPageRepository:
    """Repository for CrawledPage entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, page: CrawledPage) -> CrawledPage:
        """Save a crawled page."""
        self.table.put_item(Item=page.to_dynamo_item())
        return page

    def find_by_url_hash(self, job_id: str, url_hash: str) -> Optional[CrawledPage]:
        """Find a crawled page by URL hash."""
        response = self.table.get_item(
            Key={
                "pk": f"CrawlJob#{job_id}",
                "sk": f"Page#{url_hash}",
            }
        )
        item = response.get("Item")
        if item:
            return CrawledPage.from_dynamo_item(item)
        return None

    def find_all_by_job(
        self, job_id: str, limit: int = 100, last_evaluated_key: Optional[dict] = None
    ) -> tuple[list[CrawledPage], Optional[dict]]:
        """Find all pages for a crawl job with pagination."""
        query_params = {
            "KeyConditionExpression": Key("pk").eq(f"CrawlJob#{job_id}")
            & Key("sk").begins_with("Page#"),
            "Limit": limit,
        }

        if last_evaluated_key:
            query_params["ExclusiveStartKey"] = last_evaluated_key

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        pages = [CrawledPage.from_dynamo_item(item) for item in items]
        next_key = response.get("LastEvaluatedKey")

        return pages, next_key

    def batch_save(self, pages: list[CrawledPage]) -> None:
        """Batch save crawled pages."""
        with self.table.batch_writer() as batch:
            for page in pages:
                batch.put_item(Item=page.to_dynamo_item())
        log.info(f"Batch saved {len(pages)} crawled pages")


class ContentChunkRepository:
    """Repository for ContentChunk entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, chunk: ContentChunk) -> ContentChunk:
        """Save a content chunk."""
        self.table.put_item(Item=chunk.to_dynamo_item())
        return chunk

    def find_by_id(self, chunk_id: str, kb_id: str) -> Optional[ContentChunk]:
        """Find a content chunk by ID."""
        response = self.table.get_item(
            Key={
                "pk": f"KnowledgeBase#{kb_id}",
                "sk": f"Chunk#{chunk_id}",
            }
        )
        item = response.get("Item")
        if item:
            return ContentChunk.from_dynamo_item(item)
        return None

    def find_by_ids(self, chunk_ids: list[str], kb_id: str) -> list[ContentChunk]:
        """Find multiple content chunks by IDs (for search result retrieval)."""
        if not chunk_ids:
            return []

        # Use BatchGetItem for efficient retrieval
        keys = [
            {"pk": f"KnowledgeBase#{kb_id}", "sk": f"Chunk#{chunk_id}"}
            for chunk_id in chunk_ids
        ]

        response = self.dynamodb.batch_get_item(
            RequestItems={
                settings.dynamodb_table: {
                    "Keys": keys,
                }
            }
        )

        items = response.get("Responses", {}).get(settings.dynamodb_table, [])
        chunks = [ContentChunk.from_dynamo_item(item) for item in items]

        # Preserve order from chunk_ids
        chunk_map = {chunk.chunk_id: chunk for chunk in chunks}
        return [chunk_map[cid] for cid in chunk_ids if cid in chunk_map]

    def batch_save(self, chunks: list[ContentChunk]) -> None:
        """Batch save content chunks."""
        with self.table.batch_writer() as batch:
            for chunk in chunks:
                batch.put_item(Item=chunk.to_dynamo_item())
        log.info(f"Batch saved {len(chunks)} content chunks")

    def delete_all_by_kb(self, kb_id: str) -> int:
        """Delete all chunks for a knowledge base."""
        deleted_count = 0

        # Query all chunks
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"KnowledgeBase#{kb_id}")
            & Key("sk").begins_with("Chunk#")
        )

        items = response.get("Items", [])

        # Delete in batches
        with self.table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                deleted_count += 1

        # Handle pagination
        while response.get("LastEvaluatedKey"):
            response = self.table.query(
                KeyConditionExpression=Key("pk").eq(f"KnowledgeBase#{kb_id}")
                & Key("sk").begins_with("Chunk#"),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items = response.get("Items", [])

            with self.table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                    deleted_count += 1

        log.info(f"Deleted {deleted_count} chunks for KB {kb_id}")
        return deleted_count


class AgentKnowledgeBaseRepository:
    """Repository for AgentKnowledgeBase link entity."""

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def link(self, agent_id: str, kb_id: str, linked_by: str) -> AgentKnowledgeBase:
        """Link a knowledge base to an agent."""
        link = AgentKnowledgeBase(
            agent_id=agent_id,
            kb_id=kb_id,
            linked_by=linked_by,
        )
        self.table.put_item(Item=link.to_dynamo_item())
        log.info(f"Linked KB {kb_id} to agent {agent_id}")
        return link

    def unlink(self, agent_id: str, kb_id: str) -> bool:
        """Unlink a knowledge base from an agent."""
        try:
            self.table.delete_item(
                Key={
                    "pk": f"Agent#{agent_id}",
                    "sk": f"KnowledgeBase#{kb_id}",
                }
            )
            log.info(f"Unlinked KB {kb_id} from agent {agent_id}")
            return True
        except Exception as e:
            log.error(f"Failed to unlink KB {kb_id} from agent {agent_id}: {e}", exc_info=True)
            return False

    def find_kbs_for_agent(self, agent_id: str) -> list[AgentKnowledgeBase]:
        """Find all knowledge bases linked to an agent."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("KnowledgeBase#")
        )

        items = response.get("Items", [])
        return [AgentKnowledgeBase.from_dynamo_item(item) for item in items]

    def find_agents_for_kb(self, kb_id: str) -> list[AgentKnowledgeBase]:
        """Find all agents linked to a knowledge base (via GSI2)."""
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(f"KnowledgeBase#{kb_id}")
            & Key("gsi2_sk").begins_with("Agent#"),
        )

        items = response.get("Items", [])
        return [AgentKnowledgeBase.from_dynamo_item(item) for item in items]

    def exists(self, agent_id: str, kb_id: str) -> bool:
        """Check if a link exists between an agent and knowledge base."""
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"KnowledgeBase#{kb_id}",
            },
            ProjectionExpression="pk",  # Only retrieve the key to minimize data transfer
        )
        return "Item" in response
