"""Reporting an agent's response: the in-app report Google Play requires for AI-generated content.

A report sits in the conversation's partition beside its messages, so deleting the conversation (or the
account) deletes it too. It is keyed by message and reporter: reporting the same response twice records it
once and emails support once. See docs/LLD-mobile-ready-app.md, section 6.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from src.config import settings
from src.db import get_dynamodb_resource
from src.email import send_email
from src.email.message import EmailLink, MessageEmail

log = logging.getLogger(__name__)

REPORT_SORT_KEY_PREFIX = "REPORT#"
#: Enough of the response for support to judge it without opening the account.
EXCERPT_CHARS = 2000


class ReportReason(str, Enum):
    OFFENSIVE = "offensive"
    HARMFUL = "harmful"
    INACCURATE = "inaccurate"
    OTHER = "other"


class ReportRequest(BaseModel):
    reason: ReportReason
    note: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    reported: bool = True


class ContentReport(BaseModel):
    conversation_id: str
    message_id: str
    agent_id: str
    reporter_id: str
    reason: ReportReason
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_item(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "pk": f"CONVERSATION#{self.conversation_id}",
            "sk": f"{REPORT_SORT_KEY_PREFIX}{self.message_id}#{self.reporter_id}",
            "message_id": self.message_id,
            "agent_id": self.agent_id,
            "reporter_id": self.reporter_id,
            "reason": self.reason.value,
            "created_at": self.created_at.isoformat(),
        }
        if self.note:
            item["note"] = self.note
        return item


class ContentReportRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def add(self, report: ContentReport) -> bool:
        """Records the report; False when this person already reported this response."""
        try:
            self.table.put_item(Item=report.to_item(), ConditionExpression="attribute_not_exists(sk)")
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def list_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"CONVERSATION#{conversation_id}")
            & Key("sk").begins_with(REPORT_SORT_KEY_PREFIX)
        )
        return list(response.get("Items", []))

    def delete_for_conversation(self, conversation_id: str) -> None:
        with self.table.batch_writer() as batch:
            for item in self.list_for_conversation(conversation_id):
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})


def notify_support(report: ContentReport, excerpt: str, inbox: str) -> None:
    """Best effort: the stored report is the record, so a failed email is logged, not raised."""
    email = MessageEmail(
        preheader=f"A response was reported as {report.reason.value}.",
        heading="A response was reported",
        paragraphs=["Someone reported an agent's response in the app. The response is quoted below."],
        quote=excerpt[:EXCERPT_CHARS] or "(empty response)",
        details=[
            ("Reason", report.reason.value),
            ("Note", report.note or "(none)"),
            ("Conversation", report.conversation_id),
            ("Message", report.message_id),
            ("Agent", report.agent_id),
            ("Reporter", report.reporter_id),
        ],
        footer=EmailLink("InnomightLabs", settings.frontend_url),
    )
    if not send_email(inbox, f"Reported response ({report.reason.value})", email.text(), html=email.html()):
        log.warning("Failed to email support about a report on message %s", report.message_id)
