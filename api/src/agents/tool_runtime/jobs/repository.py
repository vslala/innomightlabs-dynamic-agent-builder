from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from src.agents.tool_runtime.jobs.models import STALE_JOB_ERROR, ToolJob, ToolJobStatus
from src.artifacts.storage import ArtifactStorage, owner_scope
from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_floats_to_decimals



#: A finished job's result stays on its DynamoDB item up to this size as JSON. A bigger one is kept in S3 instead,
#: because DynamoDB refuses items over 400 KB: a large result (an invoked agent's research, a long script output)
#: used to turn a job that had succeeded into a failure, and lose the result (KAN-67). The margin leaves room for
#: the job's own arguments and context on the same item.
INLINE_RESULT_MAX_BYTES = 200_000


class ToolJobResultStore:
    """Results too big for a job's item, as JSON in the conversation media bucket, under the owner's prefix."""

    def __init__(self, storage: ArtifactStorage | None = None):
        self._storage = storage

    @property
    def storage(self) -> ArtifactStorage:
        # Made on first use: most results are small and never need S3.
        if self._storage is None:
            self._storage = ArtifactStorage()
        return self._storage

    def save(self, job: ToolJob, body: bytes) -> str:
        key = f"users/{owner_scope(job.owner_email)}/tool-jobs/{job.job_id}/result.json"
        self.storage.put_artifact(key=key, body=body, content_type="application/json")
        return key

    def load(self, key: str) -> Any:
        return json.loads(self.storage.get_object_body(key))


class ToolJobRepository:
    def __init__(self, results: ToolJobResultStore | None = None):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)
        self.results = results or ToolJobResultStore()

    def create(self, job: ToolJob) -> ToolJob:
        self.table.put_item(
            Item=job.to_dynamo_item(),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return job

    def find_by_id(self, job_id: str) -> ToolJob | None:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(f"ToolJob#{job_id}")
            & Key("gsi2_sk").eq(f"ToolJob#{job_id}"),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        return ToolJob.from_dynamo_item(items[0])

    def mark_running(self, job_id: str, progress_message: str | None = None) -> ToolJob:
        return self._update_by_id(
            job_id,
            update_expression="SET #status = :status, started_at = :started_at, progress_message = :progress_message",
            condition_expression="#status = :queued_status",
            names={"#status": "status"},
            values={
                ":status": ToolJobStatus.RUNNING.value,
                ":queued_status": ToolJobStatus.QUEUED.value,
                ":started_at": datetime.now(timezone.utc).isoformat(),
                ":progress_message": progress_message or "Running tool job...",
            },
        )

    def mark_succeeded(self, job_id: str, result: Any) -> ToolJob:
        """Keep the result whole: on the item when it fits, otherwise in S3 with the key on the item."""
        body = json.dumps(result, default=str).encode("utf-8")
        if len(body) <= INLINE_RESULT_MAX_BYTES:
            stored, field = convert_floats_to_decimals(result), "result"
        else:
            job = self.find_by_id(job_id)
            if not job:
                raise ValueError("Tool job not found")
            stored, field = self.results.save(job, body), "result_ref"
        return self._update_by_id(
            job_id,
            update_expression="SET #status = :status, completed_at = :completed_at, #result = :result, progress_message = :progress_message",
            condition_expression="#status IN (:queued_status, :running_status)",
            names={"#status": "status", "#result": field},
            values={
                ":status": ToolJobStatus.SUCCEEDED.value,
                ":queued_status": ToolJobStatus.QUEUED.value,
                ":running_status": ToolJobStatus.RUNNING.value,
                ":completed_at": datetime.now(timezone.utc).isoformat(),
                ":result": stored,
                ":progress_message": "Tool job completed.",
            },
        )

    def with_result(self, job: ToolJob) -> ToolJob:
        """The job with a result kept in S3 read back in."""
        if job.result_ref and job.result is None:
            return job.model_copy(update={"result": self.results.load(job.result_ref)})
        return job

    def mark_failed(self, job_id: str, error: str) -> ToolJob:
        return self._update_by_id(
            job_id,
            update_expression="SET #status = :status, completed_at = :completed_at, #error = :error, progress_message = :progress_message",
            condition_expression="#status IN (:queued_status, :running_status)",
            names={"#status": "status", "#error": "error"},
            values={
                ":status": ToolJobStatus.FAILED.value,
                ":queued_status": ToolJobStatus.QUEUED.value,
                ":running_status": ToolJobStatus.RUNNING.value,
                ":completed_at": datetime.now(timezone.utc).isoformat(),
                ":error": error[:1000],
                ":progress_message": "Tool job failed.",
            },
        )

    def fail_stale_jobs(self, *, now: datetime | None = None) -> int:
        """Fail every queued/running job that has outlived the stale window.

        Execution is an in-process asyncio task, so a restart orphans the row:
        without this, an orphaned job sat RUNNING until its 7-day TTL, because
        the per-job stale check only fires when an agent happens to ask about
        that exact job id.
        """
        checked_at = now or datetime.now(timezone.utc)
        failed = 0

        for job in self._find_unfinished():
            if job.is_stale(now=checked_at):
                self.mark_failed(job.job_id, STALE_JOB_ERROR)
                failed += 1

        return failed

    def _find_unfinished(self) -> list[ToolJob]:
        scan_args: dict[str, Any] = {
            "FilterExpression": Attr("entity_type").eq("ToolJob")
            & Attr("status").is_in([ToolJobStatus.QUEUED.value, ToolJobStatus.RUNNING.value])
        }
        items: list[dict[str, Any]] = []

        while True:
            response = self.table.scan(**scan_args)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_args["ExclusiveStartKey"] = last_key

        return [ToolJob.from_dynamo_item(item) for item in items]

    def _update_by_id(
        self,
        job_id: str,
        *,
        update_expression: str,
        values: dict[str, Any],
        names: dict[str, str] | None = None,
        condition_expression: str | None = None,
    ) -> ToolJob:
        job = self.find_by_id(job_id)
        if not job:
            raise ValueError("Tool job not found")
        update_kwargs: dict[str, Any] = {
            "Key": {"pk": job.pk, "sk": job.sk},
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": values,
            "ReturnValues": "ALL_NEW",
        }
        if names:
            update_kwargs["ExpressionAttributeNames"] = names
        if condition_expression:
            update_kwargs["ConditionExpression"] = condition_expression
        try:
            response = self.table.update_item(**update_kwargs)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                current = self.find_by_id(job_id)
                if current:
                    return current
            raise
        return ToolJob.from_dynamo_item(response["Attributes"])
