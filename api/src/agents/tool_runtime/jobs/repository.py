from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.agents.tool_runtime.jobs.models import ToolJob, ToolJobStatus
from src.config import settings
from src.db import get_dynamodb_resource


class ToolJobRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

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

    def update_progress(self, job_id: str, progress_message: str) -> ToolJob:
        return self._update_by_id(
            job_id,
            update_expression="SET progress_message = :progress_message",
            values={":progress_message": progress_message},
        )

    def mark_succeeded(self, job_id: str, result: Any) -> ToolJob:
        return self._update_by_id(
            job_id,
            update_expression="SET #status = :status, completed_at = :completed_at, #result = :result, progress_message = :progress_message",
            condition_expression="#status IN (:queued_status, :running_status)",
            names={"#status": "status", "#result": "result"},
            values={
                ":status": ToolJobStatus.SUCCEEDED.value,
                ":queued_status": ToolJobStatus.QUEUED.value,
                ":running_status": ToolJobStatus.RUNNING.value,
                ":completed_at": datetime.now(timezone.utc).isoformat(),
                ":result": _convert_floats_to_decimals(result),
                ":progress_message": "Tool job completed.",
            },
        )

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


def _convert_floats_to_decimals(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_convert_floats_to_decimals(item) for item in value]
    if isinstance(value, dict):
        return {key: _convert_floats_to_decimals(item) for key, item in value.items()}
    return value
