"""Repository for scheduler entities using the project single-table pattern."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource
from src.scheduler.models import Schedule, ScheduleRun

log = logging.getLogger(__name__)


class ScheduleRunAlreadyExists(Exception):
    """Raised when a deterministic schedule run has already been recorded."""


class SchedulerRepository:
    """DynamoDB access for schedules and schedule runs."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save_schedule(self, schedule: Schedule) -> Schedule:
        existing = self.find_schedule(schedule.owner_email, schedule.schedule_id)
        if existing:
            schedule.created_at = existing.created_at
            schedule.updated_at = datetime.now(timezone.utc)

        with self.table.batch_writer() as batch:
            if existing:
                for item in existing.to_lookup_items():
                    batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            batch.put_item(Item=schedule.to_dynamo_item())
            for item in schedule.to_lookup_items():
                batch.put_item(Item=item)
        return schedule

    def find_schedule(self, owner_email: str, schedule_id: str) -> Optional[Schedule]:
        response = self.table.get_item(
            Key={"pk": f"User#{owner_email}", "sk": f"Schedule#{schedule_id}"}
        )
        item = response.get("Item")
        return Schedule.from_dynamo_item(item) if item else None

    def list_schedules(self, owner_email: str) -> list[Schedule]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{owner_email}")
            & Key("sk").begins_with("Schedule#")
        )
        schedules = [
            Schedule.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "Schedule"
        ]
        schedules.sort(key=lambda item: item.created_at, reverse=True)
        return schedules

    def list_active_schedules(self, limit: int = 1000) -> list[Schedule]:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq("ScheduleDue#active"),
            ScanIndexForward=True,
            Limit=limit,
        )
        return [
            Schedule.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "Schedule"
        ]

    def delete_schedule(self, schedule: Schedule) -> None:
        with self.table.batch_writer() as batch:
            batch.delete_item(Key={"pk": schedule.pk, "sk": schedule.sk})
            for item in schedule.to_lookup_items():
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})

    def save_run_once(self, run: ScheduleRun) -> ScheduleRun:
        try:
            self.table.put_item(
                Item=run.to_dynamo_item(),
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ScheduleRunAlreadyExists from exc
            raise
        return run

    def save_run(self, run: ScheduleRun) -> ScheduleRun:
        self.table.put_item(Item=run.to_dynamo_item())
        return run

    def list_runs(self, schedule_id: str, limit: int = 20) -> list[ScheduleRun]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Schedule#{schedule_id}")
            & Key("sk").begins_with("Run#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [
            ScheduleRun.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "ScheduleRun"
        ]
