from datetime import datetime, timezone
from typing import Optional

from ...db import get_dynamodb_resource
from ...config import settings
from .models import Subscription


class SubscriptionRepository:
    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def upsert(self, subscription: Subscription) -> Subscription:
        subscription.updated_at = datetime.utcnow().isoformat()
        self.table.put_item(Item=subscription.to_dynamo_item())
        return subscription

    def get_by_id(self, user_email: str, subscription_id: str) -> Optional[Subscription]:
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"Subscription#{subscription_id}",
            }
        )
        item = response.get("Item")
        if item:
            return Subscription.from_dynamo_item(item)
        return None

    def list_by_user(self, user_email: str) -> list[Subscription]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"User#{user_email}",
                ":sk_prefix": "Subscription#",
            },
        )
        items = response.get("Items", [])
        return [Subscription.from_dynamo_item(item) for item in items]

    def get_active_for_user(self, user_email: str) -> Optional[Subscription]:
        subscriptions = self.list_by_user(user_email)
        if not subscriptions:
            return None
        active_statuses = {"active", "trialing", "past_due"}
        active = [
            s for s in subscriptions
            if (s.status or "").lower() in active_statuses and not _is_subscription_expired(s)
        ]
        if not active:
            return None
        active.sort(key=lambda s: s.updated_at or s.created_at or "", reverse=True)
        return active[0]


class WebhookEventRepository:
    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def has_processed(self, event_id: str) -> bool:
        response = self.table.get_item(
            Key={
                "pk": f"WebhookEvent#{event_id}",
                "sk": f"WebhookEvent#{event_id}",
            }
        )
        return "Item" in response

    def mark_processed(self, event_id: str) -> None:
        self.table.put_item(
            Item={
                "pk": f"WebhookEvent#{event_id}",
                "sk": f"WebhookEvent#{event_id}",
                "event_id": event_id,
                "created_at": datetime.utcnow().isoformat(),
            }
        )


def _is_subscription_expired(subscription: Subscription) -> bool:
    period_end = _parse_period_end(subscription.current_period_end)
    if not period_end:
        return False
    return datetime.now(timezone.utc) >= period_end


def _parse_period_end(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
