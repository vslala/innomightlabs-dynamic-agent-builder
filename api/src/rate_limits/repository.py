from datetime import datetime
from typing import Optional

from ..db import get_dynamodb_resource

from ..config import settings
from .models import UsageRecord


class UsageRepository:
    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def get_usage(self, user_email: str, period_key: str) -> Optional[UsageRecord]:
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"Usage#{period_key}",
            }
        )
        item = response.get("Item")
        if item:
            return UsageRecord.from_dynamo_item(item)
        return None

    def increment_messages(self, user_email: str, period_key: str, count: int) -> UsageRecord:
        now = datetime.utcnow().isoformat()
        response = self.table.update_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"Usage#{period_key}",
            },
            UpdateExpression=(
                "SET messages_used = if_not_exists(messages_used, :zero) + :count, "
                "updated_at = :updated_at, "
                "created_at = if_not_exists(created_at, :updated_at), "
                "user_email = if_not_exists(user_email, :user_email), "
                "period_key = if_not_exists(period_key, :period_key), "
                "entity_type = if_not_exists(entity_type, :entity_type)"
            ),
            ExpressionAttributeValues={
                ":count": count,
                ":zero": 0,
                ":updated_at": now,
                ":user_email": user_email,
                ":period_key": period_key,
                ":entity_type": "Usage",
            },
            ReturnValues="ALL_NEW",
        )
        return UsageRecord.from_dynamo_item(response["Attributes"])

    def increment_kb_pages(self, user_email: str, period_key: str, count: int) -> UsageRecord:
        now = datetime.utcnow().isoformat()
        response = self.table.update_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"Usage#{period_key}",
            },
            UpdateExpression=(
                "SET kb_pages_used = if_not_exists(kb_pages_used, :zero) + :count, "
                "updated_at = :updated_at, "
                "created_at = if_not_exists(created_at, :updated_at), "
                "user_email = if_not_exists(user_email, :user_email), "
                "period_key = if_not_exists(period_key, :period_key), "
                "entity_type = if_not_exists(entity_type, :entity_type)"
            ),
            ExpressionAttributeValues={
                ":count": count,
                ":zero": 0,
                ":updated_at": now,
                ":user_email": user_email,
                ":period_key": period_key,
                ":entity_type": "Usage",
            },
            ReturnValues="ALL_NEW",
        )
        return UsageRecord.from_dynamo_item(response["Attributes"])

    def adjust_active_agents(self, user_email: str, delta: int) -> UsageRecord:
        now = datetime.utcnow().isoformat()
        response = self.table.update_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": "Usage#active",
            },
            UpdateExpression=(
                "SET agents_active = if_not_exists(agents_active, :zero) + :delta, "
                "updated_at = :updated_at, "
                "created_at = if_not_exists(created_at, :updated_at), "
                "user_email = if_not_exists(user_email, :user_email), "
                "period_key = if_not_exists(period_key, :period_key), "
                "entity_type = if_not_exists(entity_type, :entity_type)"
            ),
            ExpressionAttributeValues={
                ":delta": delta,
                ":zero": 0,
                ":updated_at": now,
                ":user_email": user_email,
                ":period_key": "active",
                ":entity_type": "Usage",
            },
            ReturnValues="ALL_NEW",
        )
        return UsageRecord.from_dynamo_item(response["Attributes"])
