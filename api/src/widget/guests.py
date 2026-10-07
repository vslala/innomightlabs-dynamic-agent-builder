"""Guest registry, conditional lifecycle transitions, and abuse limits."""
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import HTTPException
from pydantic import BaseModel

from src.config import settings
from src.db import get_dynamodb_resource
from src.rate_limits.limiter import RateLimiter, RateLimitPolicy


def guest_session_minutes(agent_timeout_minutes: int) -> int:
    """How long a guest session lasts: the agent's session timeout, or a default when it has none."""
    return agent_timeout_minutes if agent_timeout_minutes > 0 else settings.widget_guest_default_session_minutes


class GuestSessionEnded(ValueError):
    """The guest is expired, closing, or no longer exists."""


class GuestTurnInProgress(ValueError):
    """The guest's session is fine, but a reply to their previous message is still streaming."""


class GuestSession(BaseModel):
    visitor_id: str
    agent_id: str
    key_id: str
    email: str
    created_at: datetime
    last_active_at: datetime
    session_timeout_minutes: int
    session_ends_at: datetime
    origin: str = ""
    refresh_hash: str = ""
    status: str = "active"
    email_check: str = "deliverable"
    transcript: str = "pending"
    transcript_attempts: int = 0
    lease_expires_at: int = 0
    ip_hash: str = ""
    ttl: int = 0
    end_reason: str = "timeout"
    turn_id: str = ""
    turn_expires_at: int = 0
    #: Every conversation this guest created, recorded in the same transaction that creates it, so
    #: closing reads exactly these instead of searching. A DynamoDB string set: never written empty.
    conversation_ids: set[str] = set()

    @property
    def pk(self) -> str:
        return f"WidgetGuest#{self.visitor_id}"

    @property
    def sk(self) -> str:
        return "WidgetGuest#Metadata"

    @property
    def max_ends_at(self) -> datetime:
        return self.created_at + timedelta(hours=settings.widget_guest_max_lifetime_hours)

    def is_active(self, now: datetime) -> bool:
        return self.status == "active" and now < min(self.session_ends_at, self.max_ends_at)

    def to_dynamo_item(self) -> dict[str, Any]:
        return {**self.model_dump(mode="json", exclude={"conversation_ids"}), "pk": self.pk, "sk": self.sk,
                "created_at": self.created_at.isoformat(),
                "last_active_at": self.last_active_at.isoformat(),
                "session_ends_at": self.session_ends_at.isoformat(),
                "gsi2_pk": "WidgetGuestSessionEnd",
                "gsi2_sk": f"{self.session_ends_at.isoformat()}#{self.visitor_id}"}

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "GuestSession":
        return cls.model_validate(item)


class GuestSessionRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def get(self, visitor_id: str) -> GuestSession | None:
        item = self.table.get_item(Key={"pk": f"WidgetGuest#{visitor_id}", "sk": "WidgetGuest#Metadata"},
                                   ConsistentRead=True).get("Item")
        return GuestSession.from_dynamo_item(item) if item else None

    def create(self, *, agent_id: str, key_id: str, email: str, session_timeout_minutes: int,
               origin: str = "", ip: str = "", refresh_hash: str = "",
               now: datetime | None = None) -> GuestSession:
        now = now or datetime.now(timezone.utc)
        timeout = guest_session_minutes(session_timeout_minutes)
        cap = now + timedelta(hours=settings.widget_guest_max_lifetime_hours)
        session = GuestSession(visitor_id=f"guest_{uuid4().hex}", agent_id=agent_id, key_id=key_id,
            email=email, created_at=now, last_active_at=now, session_timeout_minutes=timeout,
            session_ends_at=min(now + timedelta(minutes=timeout), cap), origin=origin,
            refresh_hash=refresh_hash, ip_hash=hashlib.sha256(ip.encode()).hexdigest()[:16],
            ttl=int((cap + timedelta(hours=24)).timestamp()))
        self.table.put_item(Item=session.to_dynamo_item(), ConditionExpression="attribute_not_exists(pk)")
        return session

    def require_active(self, visitor_id: str, agent_id: str, key_id: str,
                       now: datetime | None = None) -> GuestSession:
        session = self.get(visitor_id)
        if not session or session.agent_id != agent_id or session.key_id != key_id or not session.is_active(now or datetime.now(timezone.utc)):
            raise GuestSessionEnded("guest_session_ended")
        return session

    def _update_active(self, session: GuestSession, now: datetime, expression: str,
                       values: dict[str, Any], condition: str = "") -> None:
        if not session.is_active(now):
            raise GuestSessionEnded("guest_session_ended")
        try:
            self.table.update_item(Key={"pk": session.pk, "sk": session.sk},
                UpdateExpression=expression,
                ConditionExpression="attribute_exists(pk) AND #status = :active AND session_ends_at > :now" + condition,
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":active": "active", ":now": now.isoformat(), **values})
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise GuestSessionEnded("guest_session_ended") from error
            raise

    def touch(self, session: GuestSession, now: datetime, *, turn_id: str | None = None) -> None:
        ends = min(now + timedelta(minutes=session.session_timeout_minutes), session.max_ends_at).isoformat()
        expression = "SET last_active_at = :now, session_ends_at = :ends, gsi2_sk = :sk"
        values: dict[str, Any] = {":ends": ends, ":sk": f"{ends}#{session.visitor_id}"}
        condition = ""
        if turn_id:
            expression += ", turn_id = :turn, turn_expires_at = :lease"
            values.update({":turn": turn_id, ":lease": int(now.timestamp()) + 300, ":epoch": int(now.timestamp())})
            condition = " AND (attribute_not_exists(turn_expires_at) OR turn_expires_at <= :epoch)"
        try:
            self._update_active(session, now, expression, values, condition)
        except GuestSessionEnded:
            # One condition guards both "ended" and "busy"; only a fresh read can tell them apart.
            current = self.get(session.visitor_id) if turn_id else None
            if current and current.is_active(now) and current.turn_expires_at > int(now.timestamp()):
                raise GuestTurnInProgress("guest_turn_in_progress") from None
            raise

    def heartbeat_turn(self, session: GuestSession, turn_id: str) -> None:
        self.table.update_item(Key={"pk": session.pk, "sk": session.sk},
            UpdateExpression="SET turn_expires_at = :lease",
            ConditionExpression="attribute_exists(pk) AND #status = :active AND turn_id = :turn AND turn_expires_at > :epoch",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":lease": int(datetime.now(timezone.utc).timestamp()) + 300,
                                       ":epoch": int(datetime.now(timezone.utc).timestamp()),
                                       ":active": "active", ":turn": turn_id})

    def finish_turn(self, session: GuestSession, turn_id: str) -> None:
        try:
            self.table.update_item(Key={"pk": session.pk, "sk": session.sk},
                UpdateExpression="REMOVE turn_id, turn_expires_at",
                ConditionExpression="attribute_exists(pk) AND turn_id = :turn",
                ExpressionAttributeValues={":turn": turn_id})
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def end(self, session: GuestSession, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._update_active(session, now,
            "SET session_ends_at = :now, gsi2_sk = :sk, end_reason = :reason",
            {":sk": f"{now.isoformat()}#{session.visitor_id}", ":reason": "ended_by_guest"})

    def find_ended(self, now: datetime, limit: int | None = None) -> list[GuestSession]:
        response = self.table.query(IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq("WidgetGuestSessionEnd") & Key("gsi2_sk").lt(now.isoformat() + "~"),
            Limit=limit or settings.widget_guest_sweep_batch)
        return [GuestSession.from_dynamo_item(item) for item in response.get("Items", [])]

    def claim(self, session: GuestSession, now: datetime, lease_seconds: int = 600) -> GuestSession | None:
        try:
            response = self.table.update_item(Key={"pk": session.pk, "sk": session.sk},
                UpdateExpression="SET #status = :closing, lease_expires_at = :lease",
                ConditionExpression="attribute_exists(pk) AND session_ends_at <= :now AND (#status = :active OR (#status = :closing AND lease_expires_at <= :epoch)) AND (attribute_not_exists(turn_expires_at) OR turn_expires_at <= :epoch)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":now": now.isoformat(), ":epoch": int(now.timestamp()),
                    ":active": "active", ":closing": "closing", ":lease": int(now.timestamp()) + lease_seconds},
                ReturnValues="ALL_NEW")
            return GuestSession.from_dynamo_item(response["Attributes"])
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

    def release(self, session: GuestSession) -> None:
        """Allow another sweep to retry without ever reactivating a closed identity."""
        self.table.update_item(Key={"pk": session.pk, "sk": session.sk},
            UpdateExpression="SET lease_expires_at = :zero",
            ConditionExpression="attribute_exists(pk) AND lease_expires_at = :lease",
            ExpressionAttributeValues={":zero": 0, ":lease": session.lease_expires_at})


_DAY = 86400


def _guest_limits() -> dict[str, tuple[RateLimitPolicy, str]]:
    """The guest limits and the 429 detail each returns. All fail closed: guests spend the owner's money.

    Sliding windows, so a burst across a window edge can't double the allowance. The per-key cap is a
    calendar-day fixed window because "500 per day" is how owners read it.
    """
    return {
        "GUEST_START_IP": (RateLimitPolicy.sliding_window(
            "GUEST_START_IP", limit=settings.widget_guest_start_limit,
            seconds=settings.widget_guest_start_window_seconds, fail_open=False), "guest_start_limited"),
        "GUEST_START_EMAIL": (RateLimitPolicy.sliding_window(
            "GUEST_START_EMAIL", limit=settings.widget_guest_email_daily_limit,
            seconds=_DAY, fail_open=False), "guest_start_limited"),
        "GUEST_MESSAGES": (RateLimitPolicy.sliding_window(
            "GUEST_MESSAGES", limit=settings.widget_guest_message_limit,
            seconds=settings.widget_guest_message_window_seconds, fail_open=False), "guest_message_limited"),
        "GUEST_KEY_DAILY": (RateLimitPolicy.fixed_window(
            "GUEST_KEY_DAILY", limit=settings.widget_guest_daily_message_limit,
            seconds=_DAY, fail_open=False), "guest_daily_limited"),
    }


def enforce_guest_limit(scope: str, subject: str) -> None:
    policy, detail = _guest_limits()[scope]
    decision = RateLimiter(policy).acquire(subject)
    if not decision.allowed:
        headers = {"Retry-After": str(decision.retry_after_seconds)} if decision.retry_after_seconds else None
        raise HTTPException(429, detail=detail, headers=headers)
