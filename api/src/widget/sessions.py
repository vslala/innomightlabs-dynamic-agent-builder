"""Widget visitor sign-in: the Google round trip, and the sessions it leaves behind.

The OAuth `state` is signed, expires, and carries a nonce that the browser starting the sign-in
holds in a cookie, so a sign-in only completes in the browser that began it. The callback never
puts a token in a URL: it hands over a one-time code, which the widget redeems with its key. The
refresh token is ours, stored hashed, bound to the agent, and rotated on every use. Google's
refresh token is never kept; the session does not need it.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from urllib.parse import urlsplit

import jwt
from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource
from src.widget.models import WidgetVisitor

STATE_AUDIENCE = "widget_login_state"
STATE_TTL = timedelta(minutes=10)
NONCE_COOKIE = "innomight_widget_nonce"
NONCE_COOKIE_PATH = "/widget/auth"
LOGIN_CODE_TTL_SECONDS = 120

#: The VS Code extension's own URI handler (any VS Code flavour's scheme: vscode, vscode-insiders, cursor...).
_IDE_CALLBACK = re.compile(r"^(?!https?://)[a-z][a-z0-9+.-]*://[^/?#]*\.innomightlabs-code-assist/auth-callback$")


@dataclass(frozen=True)
class SignInState:
    public_key: str
    #: Where the code goes: the IDE's URI handler, or None for the popup that posts it to its opener.
    redirect_uri: Optional[str]
    #: The origin the popup posts the code to.
    opener_origin: str


def api_origin() -> str:
    parts = urlsplit(settings.api_base_url)
    return f"{parts.scheme}://{parts.netloc}"


def is_allowed_redirect_uri(redirect_uri: str) -> bool:
    return bool(_IDE_CALLBACK.match(redirect_uri))


def create_state(sign_in: SignInState) -> tuple[str, str]:
    """(state, nonce). The nonce goes in the browser's cookie and must come back with the state."""
    nonce = secrets.token_urlsafe(16)
    payload = {
        "aud": STATE_AUDIENCE,
        "pk": sign_in.public_key,
        "redirect_uri": sign_in.redirect_uri,
        "opener_origin": sign_in.opener_origin,
        "nonce": nonce,
        "exp": datetime.now(timezone.utc) + STATE_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), nonce


def read_state(state: str | None, nonce: str | None) -> Optional[SignInState]:
    if not state or not nonce:
        return None
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE)
    except jwt.InvalidTokenError:
        return None
    if not secrets.compare_digest(str(payload.get("nonce") or ""), nonce):
        return None
    return SignInState(
        public_key=str(payload["pk"]),
        redirect_uri=payload.get("redirect_uri"),
        opener_origin=str(payload["opener_origin"]),
    )


@dataclass(frozen=True)
class VisitorSession:
    agent_id: str
    visitor: WidgetVisitor
    refresh_token: str


class WidgetSessionRepository:
    """`WidgetLoginCode#{hash}` items live two minutes; `WidgetRefresh#{hash}` items until they expire or rotate."""

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def put(self, kind: str, secret_hash: str, agent_id: str, visitor: WidgetVisitor, expires_at: int) -> None:
        self.table.put_item(Item={
            "pk": f"{kind}#{secret_hash}", "sk": f"{kind}#Metadata",
            "agent_id": agent_id, "visitor": visitor.model_dump(), "expires_at": expires_at, "ttl": expires_at,
        })

    def take(self, kind: str, secret_hash: str) -> Optional[dict[str, Any]]:
        """Delete and return the item, so each code and refresh token works once."""
        try:
            response = self.table.delete_item(
                Key={"pk": f"{kind}#{secret_hash}", "sk": f"{kind}#Metadata"},
                ConditionExpression="attribute_exists(pk)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return cast(dict[str, Any], response["Attributes"])


_LOGIN_CODE = "WidgetLoginCode"
_REFRESH = "WidgetRefresh"


def create_login_code(agent_id: str, visitor: WidgetVisitor) -> str:
    code = secrets.token_urlsafe(32)
    WidgetSessionRepository().put(_LOGIN_CODE, _hash(code), agent_id, visitor, int(time.time()) + LOGIN_CODE_TTL_SECONDS)
    return code


def redeem_login_code(code: str, agent_id: str) -> Optional[VisitorSession]:
    return _take_for_agent(_LOGIN_CODE, code, agent_id)


def rotate_refresh_token(refresh_token: str, agent_id: str, key_id: str | None = None) -> Optional[VisitorSession]:
    repository = WidgetSessionRepository()
    old_hash = _hash(refresh_token)
    item = repository.table.get_item(
        Key={"pk": f"{_REFRESH}#{old_hash}", "sk": f"{_REFRESH}#Metadata"}, ConsistentRead=True,
    ).get("Item")
    if item and item.get("visitor", {}).get("kind") == "guest":
        from src.widget.guests import GuestSessionEnded, GuestSessionRepository

        visitor = WidgetVisitor.model_validate(item["visitor"])
        try:
            guest = GuestSessionRepository().require_active(visitor.visitor_id, agent_id, key_id or "")
        except GuestSessionEnded:
            return None
        if guest.refresh_hash != old_hash or int(item["expires_at"]) <= time.time():
            return None
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        try:
            # All three writes commit together: neither a replay nor a closer can leave an orphan token.
            repository.table.meta.client.transact_write_items(TransactItems=[
                {"Delete": {"TableName": repository.table.name,
                    "Key": {"pk": f"{_REFRESH}#{old_hash}", "sk": f"{_REFRESH}#Metadata"},
                    "ConditionExpression": "attribute_exists(pk)"}},
                {"Put": {"TableName": repository.table.name, "Item": {
                    "pk": f"{_REFRESH}#{_hash(token)}", "sk": f"{_REFRESH}#Metadata",
                    "agent_id": agent_id, "visitor": visitor.model_dump(mode="json"),
                    "expires_at": int(guest.max_ends_at.timestamp()), "ttl": int(guest.max_ends_at.timestamp())}}},
                {"Update": {"TableName": repository.table.name,
                    "Key": {"pk": guest.pk, "sk": guest.sk},
                    "UpdateExpression": "SET refresh_hash = :new",
                    "ConditionExpression": "attribute_exists(pk) AND #status = :active AND session_ends_at > :now AND refresh_hash = :old",
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {":active": "active", ":now": now.isoformat(),
                        ":old": old_hash, ":new": _hash(token)}}},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                return None
            raise
        return VisitorSession(agent_id=agent_id, visitor=visitor, refresh_token=token)
    return _take_for_agent(_REFRESH, refresh_token, agent_id)


def create_guest_session(*, agent_id: str, key_id: str, email: str,
                         session_timeout_minutes: int, origin: str, ip: str) -> VisitorSession:
    from src.widget.guests import GuestSessionRepository
    from src.widget.models import WidgetVisitorKind

    token = secrets.token_urlsafe(32)
    guests = GuestSessionRepository()
    guest = guests.create(agent_id=agent_id, key_id=key_id, email=email,
        session_timeout_minutes=session_timeout_minutes, origin=origin, ip=ip, refresh_hash=_hash(token))
    visitor = WidgetVisitor(visitor_id=guest.visitor_id, email=email, kind=WidgetVisitorKind.GUEST)
    # Conditional registry update and token insertion also protect an unusually delayed start from cleanup.
    guests.table.meta.client.transact_write_items(TransactItems=[
        {"ConditionCheck": {"TableName": guests.table.name, "Key": {"pk": guest.pk, "sk": guest.sk},
            "ConditionExpression": "attribute_exists(pk) AND #status = :active AND session_ends_at > :now",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":active": "active", ":now": datetime.now(timezone.utc).isoformat()}}},
        {"Put": {"TableName": guests.table.name, "Item": {
            "pk": f"{_REFRESH}#{_hash(token)}", "sk": f"{_REFRESH}#Metadata", "agent_id": agent_id,
            "visitor": visitor.model_dump(mode="json"), "expires_at": int(guest.max_ends_at.timestamp()),
            "ttl": int(guest.max_ends_at.timestamp())}}},
    ])
    return VisitorSession(agent_id=agent_id, visitor=visitor, refresh_token=token)


def revoke_refresh_token(refresh_token: str) -> None:
    WidgetSessionRepository().take(_REFRESH, _hash(refresh_token))


def _take_for_agent(kind: str, secret: str, agent_id: str) -> Optional[VisitorSession]:
    repository = WidgetSessionRepository()
    item = repository.take(kind, _hash(secret))
    if item is None or item["agent_id"] != agent_id or int(item["expires_at"]) < time.time():
        return None
    visitor = WidgetVisitor.model_validate(item["visitor"])
    refresh_token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + settings.auth_refresh_token_days * 24 * 3600
    repository.put(_REFRESH, _hash(refresh_token), agent_id, visitor, expires_at)
    return VisitorSession(agent_id=agent_id, visitor=visitor, refresh_token=refresh_token)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
