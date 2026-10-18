"""
Repository for Knowledge Base, CrawlJob, and related entities.

Uses DynamoDB single table design with the following access patterns:

KnowledgeBase (in its account, with an owner_id; see docs/LLD-shared-accounts-and-iam.md):
    - List the account's KBs: Query pk=Account#{account_id}, sk begins_with KnowledgeBase#
    - Get KB by ID: GetItem pk=Account#{account_id}, sk=KnowledgeBase#{kb_id}
    - Create/Update KB: PutItem
    - Delete KB (soft): UpdateItem to set status=deleted

    Finding a KB is not authorizing its use: routes check the caller (`src/knowledge/access.py`).

CrawlJob:
    - List jobs for KB: Query pk=KnowledgeBase#{kb_id}, sk begins_with CrawlJob#
    - Get job by ID: GetItem pk=KnowledgeBase#{kb_id}, sk=CrawlJob#{job_id}
    - Create/Update job: PutItem

KnowledgePage:
    - List a KB's pages: Query pk=KnowledgeBase#{kb_id}, sk begins_with KnowledgePage#
    - Save: PutItem, conditional on the version it was read at

CrawlLease:
    - Claim / renew: PutItem pk=KnowledgeBase#{kb_id}, sk=CrawlLease, if free, lapsed, or already this job's
    - Release: DeleteItem, if still this job's

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

from ..db import get_dynamodb_resource
import base64
import json
from collections import Counter
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from typing import Any, Optional
import logging

from src.config import settings
from src.knowledge.models import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    CrawlJob,
    CrawlLease,
    KnowledgePage,
    KnowledgePageState,
    url_hash,
    CrawlStep,
    CrawledPage,
    ContentChunk,
    ContentUpload,
    AgentKnowledgeBase,
)
from src.common.pagination import InvalidCursor, decode_cursor, encode_cursor

log = logging.getLogger(__name__)

#: DynamoDB's BatchGetItem takes at most this many keys.
BATCH_GET_LIMIT = 100


class KnowledgeBaseRepository:
    """Repository for KnowledgeBase entity."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, kb: KnowledgeBase) -> KnowledgeBase:
        """Create or update; an update keeps the original created_at."""
        existing = self.find_in_account(kb.account_id, kb.kb_id)

        if existing:
            kb.created_at = existing.created_at
            kb.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=kb.to_dynamo_item())
        log.info(f"Saved knowledge base {kb.kb_id} in account {kb.account_id}")
        return kb

    def find_in_account(self, account_id: str, kb_id: str) -> Optional[KnowledgeBase]:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"KnowledgeBase#{kb_id}"}).get("Item")
        return KnowledgeBase.from_dynamo_item(item) if item else None

    def list_in_account(self, account_id: str, include_deleted: bool = False) -> list[KnowledgeBase]:
        """Every knowledge base in the account, whoever owns it; callers filter to what the caller may see."""
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("KnowledgeBase#")
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        kbs = [KnowledgeBase.from_dynamo_item(item) for item in items]
        return kbs if include_deleted else [kb for kb in kbs if kb.status != KnowledgeBaseStatus.DELETED]

    def list_owned(self, account_id: str, owner_id: str, include_deleted: bool = False) -> list[KnowledgeBase]:
        """The knowledge bases one member owns in an account."""
        return [kb for kb in self.list_in_account(account_id, include_deleted) if kb.owner_id == owner_id]

    def soft_delete(self, account_id: str, kb_id: str) -> bool:
        """Soft delete a knowledge base by setting status to deleted."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"Account#{account_id}",
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

    def update_stats(self, account_id: str, kb_id: str, total_pages: int, total_chunks: int, total_vectors: int) -> bool:
        """Update knowledge base statistics after a crawl."""
        try:
            self.table.update_item(
                Key={
                    "pk": f"Account#{account_id}",
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
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, job: CrawlJob) -> CrawlJob:
        """Save a crawl job."""
        self.table.put_item(Item=job.to_dynamo_item())
        log.info(f"Saved crawl job {job.job_id} for KB {job.kb_id}")
        return job

    def save_if_in_progress(self, job: CrawlJob) -> bool:
        """Save worker-owned state without overwriting a terminal status."""
        return self.save_if_status(job, expected_status="in_progress")

    def save_if_status(self, job: CrawlJob, *, expected_status: str) -> bool:
        """Save a job only when its persisted status matches the worker's view."""
        job.updated_at = datetime.now(timezone.utc)
        try:
            self.table.put_item(
                Item=job.to_dynamo_item(),
                ConditionExpression="#status = :expected_status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":expected_status": expected_status},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def update_heartbeat(self, job_id: str, kb_id: str, heartbeat_at: datetime, progress: dict) -> bool:
        """Record worker liveness and progress while the job is active."""
        timestamp = heartbeat_at.isoformat()
        try:
            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression=(
                    "SET last_heartbeat_at = :heartbeat, updated_at = :heartbeat, progress = :progress"
                ),
                ConditionExpression="#status = :in_progress",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":heartbeat": timestamp,
                    ":progress": progress,
                    ":in_progress": "in_progress",
                },
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def find_in_progress(self) -> list[CrawlJob]:
        """Return all running crawl jobs for the global stale-job reaper."""
        scan_args: dict[str, Any] = {
            "FilterExpression": (
                Attr("entity_type").eq("CrawlJob") & Attr("status").eq("in_progress")
            )
        }
        items: list[dict] = []

        while True:
            response = self.table.scan(**scan_args)
            items.extend(response.get("Items", []))
            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break
            scan_args["ExclusiveStartKey"] = last_evaluated_key

        return [CrawlJob.from_dynamo_item(item) for item in items]

    def mark_failed_if_heartbeat_unchanged(
        self,
        job: CrawlJob,
        *,
        failed_at: datetime,
        error_message: str,
    ) -> bool:
        """Fail a stale job only if no newer heartbeat won the race."""
        expression_values = {
            ":in_progress": "in_progress",
            ":failed": "failed",
            ":failed_at": failed_at.isoformat(),
            ":error": error_message,
        }
        if job.last_heartbeat_at is not None:
            condition = "#status = :in_progress AND last_heartbeat_at = :observed_heartbeat"
            expression_values[":observed_heartbeat"] = job.last_heartbeat_at.isoformat()
        else:
            # `last_heartbeat_at` is stored as an explicit NULL (not omitted) for jobs
            # that have never heartbeated, so both checks are needed.
            condition = (
                "#status = :in_progress AND "
                "(attribute_not_exists(last_heartbeat_at) OR last_heartbeat_at = :empty_heartbeat)"
            )
            expression_values[":empty_heartbeat"] = None

        try:
            self.table.update_item(
                Key={"pk": job.pk, "sk": job.sk},
                UpdateExpression=(
                    "SET #status = :failed, error_message = :error, "
                    "updated_at = :failed_at, timing.completed_at = :failed_at"
                ),
                ConditionExpression=condition,
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues=expression_values,
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

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

    def find_all_by_kb(self, kb_id: str, limit: Optional[int] = 5) -> list[CrawlJob]:
        """The knowledge base's newest crawl jobs, newest first; all of them with `limit=None`."""
        # Job keys are random ids, so the newest can be anywhere in the partition: read it all, then sort.
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("CrawlJob#")
        }
        jobs: list[CrawlJob] = []
        while True:
            response = self.table.query(**query)
            jobs += [CrawlJob.from_dynamo_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def find_page_by_kb(self, kb_id: str, limit: int, cursor: Optional[str] = None) -> tuple[list[CrawlJob], Optional[str]]:
        """A page of the knowledge base's jobs, newest first, and the cursor of the next (None after the last).

        The cursor is the `created_at` of the page's last job: job keys are random, so time is the only order.
        """
        jobs = self.find_all_by_kb(kb_id, limit=None)
        if start := decode_cursor(cursor, key_names=("created_at",)):
            try:
                after = datetime.fromisoformat(start["created_at"])
            except ValueError as exc:
                raise InvalidCursor("Invalid pagination cursor") from exc
            jobs = [job for job in jobs if job.created_at < after]
        shown = jobs[:limit]
        return shown, encode_cursor({"created_at": shown[-1].created_at.isoformat()}) if len(jobs) > limit else None

    def cancel_if_active(self, job_id: str, kb_id: str) -> bool:
        """Cancel a pending or running job without overwriting a terminal state."""
        cancelled_at = datetime.now(timezone.utc).isoformat()
        try:
            self.table.update_item(
                Key={
                    "pk": f"KnowledgeBase#{kb_id}",
                    "sk": f"CrawlJob#{job_id}",
                },
                UpdateExpression=(
                    "SET #status = :cancelled, updated_at = :cancelled_at, "
                    "timing.completed_at = :cancelled_at"
                ),
                ConditionExpression="#status IN (:pending, :in_progress)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":cancelled": "cancelled",
                    ":cancelled_at": cancelled_at,
                    ":pending": "pending",
                    ":in_progress": "in_progress",
                },
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

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


#: Marks a knowledge base whose older chunks have been given pages.
ADOPTED_SK = "KnowledgePagesAdopted"


_LISTING_ORDER = {
    KnowledgePageState.FAILING: 1, KnowledgePageState.LIVE: 2, KnowledgePageState.DUPLICATE: 3, KnowledgePageState.GONE: 4,
}


def _listing_place(page: KnowledgePage) -> tuple[int, str]:
    """Where a page stands in the page list: those that need a look (0), then each state in turn, by address."""
    return (0 if page.needs_attention else _LISTING_ORDER[page.state], page.url)


class PageWrittenElsewhere(RuntimeError):
    """Another writer saved the page since it was read: this write would have undone theirs."""


class KnowledgePageRepository:
    """What each page of a knowledge base has in it now (`KnowledgePage`)."""

    def __init__(self):
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def list_by_kb(self, kb_id: str) -> list[KnowledgePage]:
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("KnowledgePage#")
        }
        pages: list[KnowledgePage] = []
        while True:
            response = self.table.query(**query)
            pages += [KnowledgePage.from_dynamo_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                return pages
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def find(self, kb_id: str, url: str) -> Optional[KnowledgePage]:
        item = self.table.get_item(Key={"pk": f"KnowledgeBase#{kb_id}", "sk": f"KnowledgePage#{url_hash(url)}"}).get("Item")
        return KnowledgePage.from_dynamo_item(item) if item else None

    def duplicates_of(self, kb_id: str, url: str) -> list[str]:
        """The addresses of the pages whose text is this page's, and so have no chunks of their own."""
        return sorted(
            page.url for page in self.list_by_kb(kb_id)
            if page.state == KnowledgePageState.DUPLICATE and page.duplicate_of == url
        )

    def count_by_state(self, kb_id: str) -> dict[KnowledgePageState, int]:
        """How many pages the knowledge base has in each state."""
        counts = Counter(page.state for page in self.list_by_kb(kb_id))
        return {state: counts[state] for state in KnowledgePageState}

    def list_page(
        self, kb_id: str, *, state: Optional[KnowledgePageState] = None, search: str = "", limit: int, cursor: Optional[str] = None
    ) -> tuple[list[KnowledgePage], Optional[str]]:
        """A page of the knowledge base's pages, and the cursor of the next (None after the last).

        Pages that need a look come first, then failing, live, duplicate and removed ones, each by address. The cursor
        is the last page's place in that order, so it holds when pages change between requests.
        """
        needle = search.strip().lower()
        pages = [
            page for page in self.list_by_kb(kb_id)
            if (state is None or page.state == state) and needle in f"{page.url} {page.title}".lower()
        ]
        pages.sort(key=_listing_place)
        if start := decode_cursor(cursor, key_names=("rank", "url")):
            pages = [page for page in pages if _listing_place(page) > (int(start["rank"]), start["url"])]
        shown = pages[:limit]
        last = _listing_place(shown[-1]) if len(pages) > limit else None
        return shown, encode_cursor({"rank": str(last[0]), "url": last[1]}) if last else None

    def save(self, page: KnowledgePage) -> KnowledgePage:
        """The page as written, with its next version; `PageWrittenElsewhere` if it changed since it was read."""
        written = page.model_copy(update={"version": page.version + 1})
        condition = (
            {"ConditionExpression": "attribute_not_exists(pk)"} if page.version == 0
            else {"ConditionExpression": "version = :read", "ExpressionAttributeValues": {":read": page.version}}
        )
        try:
            self.table.put_item(Item=written.to_dynamo_item(), **condition)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise PageWrittenElsewhere(f"{page.url} was written by another crawl") from exc
            raise
        return written

    def adopted(self, kb_id: str) -> bool:
        """Whether the knowledge base's chunks from before pages were kept have been given pages (see `adopt`)."""
        return "Item" in self.table.get_item(Key={"pk": f"KnowledgeBase#{kb_id}", "sk": ADOPTED_SK})

    def mark_adopted(self, kb_id: str) -> None:
        self.table.put_item(Item={
            "pk": f"KnowledgeBase#{kb_id}", "sk": ADOPTED_SK, "kb_id": kb_id,
            "adopted_at": datetime.now(timezone.utc).isoformat(), "entity_type": "KnowledgePagesAdopted",
        })

    def delete_all_by_kb(self, kb_id: str) -> None:
        with self.table.batch_writer() as batch:
            for page in self.list_by_kb(kb_id):
                batch.delete_item(Key={"pk": page.pk, "sk": page.sk})
            batch.delete_item(Key={"pk": f"KnowledgeBase#{kb_id}", "sk": ADOPTED_SK})


class CrawlLeaseRepository:
    """The single crawl a knowledge base runs at a time (`CrawlLease`)."""

    def __init__(self):
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def claim(self, lease: CrawlLease, *, now: datetime) -> bool:
        """Take the lease for `lease.job_id`, or renew it: only when no other job holds one that hasn't lapsed."""
        try:
            self.table.put_item(
                Item=lease.to_dynamo_item(),
                ConditionExpression="attribute_not_exists(pk) OR job_id = :job_id OR expires_at < :now",
                ExpressionAttributeValues={":job_id": lease.job_id, ":now": now.isoformat()},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def find(self, kb_id: str) -> Optional[CrawlLease]:
        item = self.table.get_item(Key={"pk": f"KnowledgeBase#{kb_id}", "sk": "CrawlLease"}).get("Item")
        return CrawlLease.from_dynamo_item(item) if item else None

    def release(self, kb_id: str, job_id: str) -> None:
        """Let the knowledge base crawl again, unless another job has taken the lease since."""
        try:
            self.table.delete_item(
                Key={"pk": f"KnowledgeBase#{kb_id}", "sk": "CrawlLease"},
                ConditionExpression="job_id = :job_id",
                ExpressionAttributeValues={":job_id": job_id},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise


class CrawlStepRepository:
    """Repository for CrawlStep (audit log) entity."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
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
        self.dynamodb = get_dynamodb_resource()
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
        self.dynamodb = get_dynamodb_resource()
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
        """The chunks that exist of these ids, in their order (search, and reading a page's chunks)."""
        found: dict[str, ContentChunk] = {}
        for start in range(0, len(chunk_ids), BATCH_GET_LIMIT):
            request: dict[str, Any] = {settings.dynamodb_table: {"Keys": [
                {"pk": f"KnowledgeBase#{kb_id}", "sk": f"Chunk#{chunk_id}"}
                for chunk_id in chunk_ids[start:start + BATCH_GET_LIMIT]
            ]}}
            # DynamoDB may hand back part of a batch as unprocessed when it's busy: ask again for those
            while request:
                response = self.dynamodb.batch_get_item(RequestItems=request)
                for item in response.get("Responses", {}).get(settings.dynamodb_table, []):
                    found[item["chunk_id"]] = ContentChunk.from_dynamo_item(item)
                request = response.get("UnprocessedKeys") or {}
        return [found[chunk_id] for chunk_id in chunk_ids if chunk_id in found]

    def batch_save(self, chunks: list[ContentChunk]) -> None:
        """Batch save content chunks."""
        with self.table.batch_writer() as batch:
            for chunk in chunks:
                batch.put_item(Item=chunk.to_dynamo_item())
        log.info(f"Batch saved {len(chunks)} content chunks")

    def has_any(self, kb_id: str) -> bool:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("Chunk#"),
            Limit=1,
        )
        return bool(response.get("Items"))

    def find_all_by_kb(self, kb_id: str) -> list[ContentChunk]:
        """Every chunk of a knowledge base."""
        query = {"KeyConditionExpression": Key("pk").eq(f"KnowledgeBase#{kb_id}") & Key("sk").begins_with("Chunk#")}
        chunks: list[ContentChunk] = []
        while True:
            response = self.table.query(**query)
            chunks += [ContentChunk.from_dynamo_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                return chunks
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def delete_by_ids(self, kb_id: str, chunk_ids: list[str]) -> None:
        with self.table.batch_writer() as batch:
            for chunk_id in chunk_ids:
                batch.delete_item(Key={"pk": f"KnowledgeBase#{kb_id}", "sk": f"Chunk#{chunk_id}"})

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


class ContentUploadRepository:
    """Repository for ContentUpload entity."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, upload: ContentUpload) -> ContentUpload:
        """Save a content upload record."""
        self.table.put_item(Item=upload.to_dynamo_item())
        log.info(f"Saved content upload {upload.upload_id} for KB {upload.kb_id}")
        return upload

    def list_by_kb_paginated(
        self,
        kb_id: str,
        limit: int = 10,
        cursor: Optional[str] = None,
        newest_first: bool = True,
    ) -> tuple[list[ContentUpload], Optional[str], bool]:
        """
        List content uploads for a knowledge base with pagination.

        Returns uploads ordered by created_at (newest_first by default).
        """
        query_params = {
            "KeyConditionExpression": (
                Key("pk").eq(f"KnowledgeBase#{kb_id}")
                & Key("sk").begins_with("Upload#")
            ),
            "Limit": limit,
            "ScanIndexForward": not newest_first,
        }

        if cursor:
            query_params["ExclusiveStartKey"] = decode_cursor(cursor)

        response = self.table.query(**query_params)

        items = response.get("Items", [])
        uploads = [ContentUpload.from_dynamo_item(item) for item in items]

        last_evaluated_key = response.get("LastEvaluatedKey")
        has_more = last_evaluated_key is not None

        next_cursor = None
        if has_more and last_evaluated_key:
            next_cursor = base64.b64encode(
                json.dumps(last_evaluated_key).encode("utf-8")
            ).decode("utf-8")

        return uploads, next_cursor, has_more


class AgentKnowledgeBaseRepository:
    """Repository for AgentKnowledgeBase link entity."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
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
