import logging
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
import httpx

from src.config import settings
from src.notifications.email import send_email
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


def _dedupe_email_event(table, user_email: str, event_id: str, event_type: str) -> bool:
    try:
        table.put_item(
            Item={
                "pk": f"User#{user_email}",
                "sk": f"EmailEvent#{event_id}",
                "entity_type": "EmailEvent",
                "event_type": event_type,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _stripe_get(path: str) -> Optional[dict[str, Any]]:
    if not settings.stripe_secret_key:
        return None
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code >= 400:
            log.warning("Stripe API error %s: %s", response.status_code, response.text)
            return None
        return response.json()
    except Exception as exc:
        log.warning("Stripe API request failed: %s", exc)
        return None


def _get_invoice_url(subscription_id: str, invoice_id: Optional[str]) -> Optional[str]:
    if invoice_id:
        invoice = _stripe_get(f"/invoices/{invoice_id}")
        if invoice:
            return invoice.get("hosted_invoice_url") or invoice.get("invoice_pdf")
    invoice_list = _stripe_get(f"/invoices?subscription={subscription_id}&limit=1")
    if invoice_list:
        data = invoice_list.get("data", [])
        if data:
            return data[0].get("hosted_invoice_url") or data[0].get("invoice_pdf")
    return None


def _send_welcome_email(user_email: str, name: Optional[str]) -> None:
    subject = "Welcome to Innomightlabs"
    greeting = name or user_email.split("@")[0]
    body = (
        f"Hi {greeting},\n\n"
        "Welcome to Innomightlabs. Your account is ready, and you can start building agents right away.\n\n"
        "If you need help, just reply to this email.\n\n"
        "Thanks,\n"
        "The Innomightlabs Team"
    )
    send_email(user_email, subject, body)


def _send_invoice_email(user_email: str, invoice_url: str) -> None:
    subject = "Your Innomightlabs payment receipt"
    body = (
        "Hi,\n\n"
        "Thanks for your payment. You can view or download your invoice here:\n"
        f"{invoice_url}\n\n"
        "If you have any questions, just reply to this email.\n\n"
        "Thanks,\n"
        "The Innomightlabs Team"
    )
    send_email(user_email, subject, body)


def _is_user_record(image: dict[str, Any]) -> bool:
    return image.get("sk") == "User#Metadata"


def _is_subscription_record(image: dict[str, Any]) -> bool:
    sk = image.get("sk", "")
    return isinstance(sk, str) and sk.startswith("Subscription#")


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
        if not image:
            continue

        if new_image and event_name == "INSERT" and _is_user_record(new_image):
            user_email = new_image.get("email")
            if user_email and _dedupe_email_event(table, user_email, event_id, "welcome"):
                _send_welcome_email(user_email, new_image.get("name"))

        if new_image and _is_subscription_record(new_image):
            user_email = new_image.get("user_email")
            subscription_id = new_image.get("subscription_id")
            invoice_id = new_image.get("latest_invoice_id")
            invoice_changed = invoice_id != old_image.get("latest_invoice_id") if old_image else True
            if (
                user_email
                and subscription_id
                and invoice_changed
                and _dedupe_email_event(table, user_email, event_id, "invoice")
            ):
                invoice_url = _get_invoice_url(subscription_id, invoice_id)
                if invoice_url:
                    _send_invoice_email(user_email, invoice_url)

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
