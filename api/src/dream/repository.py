"""DynamoDB repository for Dream settings, progress, runs, and audit records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key

from src.config import settings
from src.db import get_dynamodb_resource
from src.dream.models import DreamActionLog, DreamCursor, DreamRun, DreamRunStatus, DreamSettings


class DreamRepository:
    """Persist Dream entities using their explicitly scoped single-table keys."""

    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save_settings(self, dream_settings: DreamSettings) -> DreamSettings:
        existing = self.find_settings(dream_settings.user_email)
        if existing:
            dream_settings.created_at = existing.created_at
            dream_settings.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=dream_settings.to_dynamo_item())
        return dream_settings

    def find_settings(self, user_email: str) -> DreamSettings | None:
        response = self.table.get_item(Key={"pk": f"User#{user_email}", "sk": "DreamSettings"})
        item = response.get("Item")
        return DreamSettings.from_dynamo_item(item) if item else None

    def save_cursor(self, cursor: DreamCursor) -> DreamCursor:
        cursor.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=cursor.to_dynamo_item())
        return cursor

    def find_cursor(self, agent_id: str, user_id: str) -> DreamCursor | None:
        response = self.table.get_item(
            Key={"pk": f"Agent#{agent_id}#User#{user_id}", "sk": "DreamCursor"}
        )
        item = response.get("Item")
        return DreamCursor.from_dynamo_item(item) if item else None

    def save_run(self, run: DreamRun) -> DreamRun:
        self.table.put_item(Item=run.to_dynamo_item())
        return run

    def try_acquire_run_lease(self, agent_id: str, user_id: str, run_id: str, lease_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_seconds)
        try:
            self.table.put_item(
                Item={
                    "pk": f"Agent#{agent_id}#User#{user_id}",
                    "sk": "DreamRunLease",
                    "entity_type": "DreamRunLease",
                    "run_id": run_id,
                    "lease_expires_at": int(expires_at.timestamp()),
                    # DynamoDB TTL cleans up abandoned leases eventually; the conditional
                    # expression is the immediate expiration mechanism.
                    "ttl": int(expires_at.timestamp()),
                },
                ConditionExpression="attribute_not_exists(pk) OR lease_expires_at < :now",
                ExpressionAttributeValues={":now": int(now.timestamp())},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def renew_run_lease(self, agent_id: str, user_id: str, run_id: str, lease_seconds: int) -> bool:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        try:
            self.table.update_item(
                Key={"pk": f"Agent#{agent_id}#User#{user_id}", "sk": "DreamRunLease"},
                UpdateExpression="SET lease_expires_at = :expires_at, #ttl = :ttl",
                ConditionExpression="run_id = :run_id",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":expires_at": int(expires_at.timestamp()),
                    ":ttl": int(expires_at.timestamp()),
                    ":run_id": run_id,
                },
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def release_run_lease(self, agent_id: str, user_id: str, run_id: str) -> None:
        try:
            self.table.delete_item(
                Key={"pk": f"Agent#{agent_id}#User#{user_id}", "sk": "DreamRunLease"},
                ConditionExpression="run_id = :run_id",
                ExpressionAttributeValues={":run_id": run_id},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise

    def list_runs(self, agent_id: str, user_id: str, limit: int = 20) -> list[DreamRun]:
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"Agent#{agent_id}#User#{user_id}")
                & Key("sk").begins_with("DreamRun#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [
            DreamRun.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "DreamRun"
        ]

    def fail_stale_runs(self) -> int:
        """Finalize `DreamRun` rows left `running` by a worker that died without releasing its lease.

        Runs on the periodic reaper (see `scheduler/runtime.py`), not on the `dream()` hot path, so
        correction doesn't wait for another dream() call to happen to fire for the same agent/user.
        A run is stale exactly when it no longer holds a current `DreamRunLease` — reusing that
        lease's own liveness signal instead of a second, independent staleness calculation.
        """
        completed_at = datetime.now(timezone.utc)
        failed = 0
        for run in self._scan_running_runs():
            if self._lease_is_current(run.agent_id, run.user_id, run.run_id):
                continue
            if self._mark_failed_if_still_running(run, completed_at):
                failed += 1
        return failed

    def _scan_running_runs(self) -> list[DreamRun]:
        scan_args: dict = {
            "FilterExpression": Attr("entity_type").eq("DreamRun") & Attr("status").eq(DreamRunStatus.RUNNING.value)
        }
        items: list[dict] = []
        while True:
            response = self.table.scan(**scan_args)
            items.extend(response.get("Items", []))
            last_evaluated_key = response.get("LastEvaluatedKey")
            if not last_evaluated_key:
                break
            scan_args["ExclusiveStartKey"] = last_evaluated_key
        return [DreamRun.from_dynamo_item(item) for item in items]

    def _lease_is_current(self, agent_id: str, user_id: str, run_id: str) -> bool:
        response = self.table.get_item(Key={"pk": f"Agent#{agent_id}#User#{user_id}", "sk": "DreamRunLease"})
        item = response.get("Item")
        if not item or item.get("run_id") != run_id:
            return False
        return int(item["lease_expires_at"]) > int(datetime.now(timezone.utc).timestamp())

    def _mark_failed_if_still_running(self, run: DreamRun, completed_at: datetime) -> bool:
        try:
            self.table.update_item(
                Key={"pk": run.pk, "sk": run.sk},
                UpdateExpression="SET #status = :failed, #error = :error, completed_at = :completed_at",
                ConditionExpression="#status = :running",
                ExpressionAttributeNames={"#status": "status", "#error": "error"},
                ExpressionAttributeValues={
                    ":failed": DreamRunStatus.FAILED.value,
                    ":running": DreamRunStatus.RUNNING.value,
                    ":error": "Dream worker stopped before the run completed",
                    ":completed_at": completed_at.isoformat(),
                },
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def save_action_log(self, action_log: DreamActionLog) -> DreamActionLog:
        self.table.put_item(Item=action_log.to_dynamo_item())
        return action_log

    def list_action_logs(self, run_id: str) -> list[DreamActionLog]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"DreamRun#{run_id}")
            & Key("sk").begins_with("Action#"),
            ScanIndexForward=True,
        )
        return [
            DreamActionLog.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "DreamActionLog"
        ]


def get_dream_repository() -> DreamRepository:
    return DreamRepository()
