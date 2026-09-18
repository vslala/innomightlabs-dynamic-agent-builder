"""DynamoDB repository for Dream settings, progress, runs, and audit records."""

from __future__ import annotations

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.db import get_dynamodb_resource
from src.dream.models import DreamActionLog, DreamCursor, DreamRun, DreamSettings


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
