import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, cast

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
import httpx

from src.config import settings
from src.db import get_dynamodb_resource
from src.conversations.repository import ConversationRepository
from src.email import send_email
from src.rate_limits.billing import account_billing_email
from src.rate_limits.repository import UsageRepository

logging.basicConfig(level=os.getenv("LOG_LEVEL", "ERROR").upper())
log = logging.getLogger(__name__)

deserializer = TypeDeserializer()


def _deserialize(image: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not image:
        return {}
    return {key: deserializer.deserialize(value) for key, value in image.items()}


@dataclass(frozen=True)
class UsageMeter:
    """How one kind of item spends a plan quota: which change uses a unit, when, and who pays for it.

    Usage is the account owner's, by email, until billing moves to accounts (KAN-86). Agents have no meter: the
    limit counts the agents in the owner's accounts when one is created.
    """

    entity_type: str
    #: The month the change uses one unit in, or None when it uses nothing
    period: Callable[[str, dict[str, Any], dict[str, Any]], Optional[str]]
    #: Who the unit is charged to: the owner of the account it happened in, whoever did it
    billed_email: Callable[[dict[str, Any]], Optional[str]]
    record: Callable[[UsageRepository, str, str], Any]


def _message_period(event_name: str, _old: dict[str, Any], new: dict[str, Any]) -> Optional[str]:
    created_at = new.get("created_at")
    return _period_key(created_at) if event_name == "INSERT" and created_at else None


def _message_billed_email(image: dict[str, Any]) -> Optional[str]:
    conversation_id = image.get("conversation_id")
    conversation = ConversationRepository().get(conversation_id) if conversation_id else None
    # A message whose conversation can't be found is charged to whoever wrote it, as before accounts
    return account_billing_email(conversation.account_id) if conversation else image.get("created_by")


def _page_period(event_name: str, old: dict[str, Any], new: dict[str, Any]) -> Optional[str]:
    """A page counts once, when it first succeeds: inserted as a success, or a pending page finishing."""
    became_success = new.get("status") == "success" and (event_name == "INSERT" or (
        event_name == "MODIFY" and old.get("status") != "success"))
    crawled_at = new.get("crawled_at")
    return _period_key(crawled_at) if became_success and crawled_at else None


def _page_billed_email(image: dict[str, Any]) -> Optional[str]:
    # Pages from before they recorded their account have none, and are charged to no one
    account_id = image.get("account_id")
    return account_billing_email(account_id) if account_id else None


USAGE_METERS: dict[str, UsageMeter] = {meter.entity_type: meter for meter in (
    UsageMeter("Message", _message_period, _message_billed_email,
               lambda usage, email, period: usage.increment_messages(email, period, 1)),
    UsageMeter("CrawledPage", _page_period, _page_billed_email,
               lambda usage, email, period: usage.increment_kb_pages(email, period, 1)),
)}


def _period_key(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date)
    except ValueError:
        log.warning("Invalid timestamp format: %s, using current time", iso_date)
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
        payload = response.json()
        return cast(dict[str, Any], payload) if isinstance(payload, dict) else None
    except Exception as exc:
        log.warning("Stripe API request failed: %s", exc)
        return None


def _get_invoice_url(subscription_id: str, invoice_id: Optional[str]) -> Optional[str]:
    if invoice_id:
        invoice = _stripe_get(f"/invoices/{invoice_id}")
        if invoice:
            url = invoice.get("hosted_invoice_url") or invoice.get("invoice_pdf")
            return str(url) if url else None
    invoice_list = _stripe_get(f"/invoices?subscription={subscription_id}&limit=1")
    if invoice_list:
        data = invoice_list.get("data", [])
        if data:
            url = data[0].get("hosted_invoice_url") or data[0].get("invoice_pdf")
            return str(url) if url else None
    return None



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



def _is_subscription_record(image: dict[str, Any]) -> bool:
    sk = image.get("sk", "")
    return isinstance(sk, str) and sk.startswith("Subscription#")


def handler(event, context):  # noqa: ARG001
    dynamodb = get_dynamodb_resource()
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

        # Signup owns app-specific welcome emails; identity inserts must not send a second one.
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

        meter = USAGE_METERS.get(image.get("entity_type", ""))
        period = meter.period(event_name, old_image, new_image) if meter and new_image else None
        if meter is None or period is None:
            continue

        user_email = meter.billed_email(image)
        if not user_email:
            log.warning("Usage event has no account to charge", extra={"event_id": event_id, "entity_type": meter.entity_type})
            continue
        if not _dedupe_event(table, user_email, event_id, meter.entity_type):
            log.warning(
                "Duplicate usage event skipped",
                extra={"user": user_email, "event_id": event_id, "entity_type": meter.entity_type},
            )
            continue

        meter.record(usage_repo, user_email, period)
        log.debug("Recorded usage", extra={"user": user_email, "period": period, "entity_type": meter.entity_type})

    return {"status": "ok"}
