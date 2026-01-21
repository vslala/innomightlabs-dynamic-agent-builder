import logging
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from src.config import settings
from src.rate_limits.repository import UsageRepository

log = logging.getLogger(__name__)

deserializer = TypeDeserializer()


def _deserialize(image: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not image:
        return {}
    return {key: deserializer.deserialize(value) for key, value in image.items()}


def _period_key(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m")


def _dedupe_event(table, user_email: str, event_id: str, entity_type: str) -> bool:
    try:
        table.put_item(
            Item={
                "pk": f"User#{user_email}",
                "sk": f"UsageEvent#{event_id}",
                "entity_type": "UsageEvent",
                "event_type": entity_type,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def handler(event, context):  # noqa: ARG001
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    table = dynamodb.Table(settings.dynamodb_table)
    usage_repo = UsageRepository()

    for record in event.get("Records", []):
        event_name = record.get("eventName")
        event_id = record.get("eventID", "")
        dynamodb_record = record.get("dynamodb", {})
        new_image = _deserialize(dynamodb_record.get("NewImage"))
        old_image = _deserialize(dynamodb_record.get("OldImage"))

        image = new_image or old_image
        entity_type = image.get("entity_type")
        if entity_type not in {"Agent", "Message", "CrawledPage"}:
            continue

        user_email = image.get("created_by")
        if not user_email:
            continue

        if not _dedupe_event(table, user_email, event_id, entity_type):
            continue

        if entity_type == "Agent":
            if event_name == "INSERT":
                usage_repo.adjust_active_agents(user_email, 1)
            elif event_name == "REMOVE":
                usage_repo.adjust_active_agents(user_email, -1)
            continue

        if entity_type == "Message" and event_name == "INSERT":
            created_at = image.get("created_at")
            if created_at:
                period_key = _period_key(created_at)
                usage_repo.increment_messages_for_period(user_email, period_key, 1)
            continue

        if entity_type == "CrawledPage" and event_name == "INSERT":
            status = image.get("status")
            if status != "success":
                continue
            crawled_at = image.get("crawled_at")
            if crawled_at:
                period_key = _period_key(crawled_at)
                usage_repo.increment_kb_pages_for_period(user_email, period_key, 1)

    return {"status": "ok"}
