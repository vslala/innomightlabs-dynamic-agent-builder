"""Login codes and refresh tokens for the apps that share this login (see auth/apps.py).

An app's backend redeems a one-time login code for an access token and a refresh token, then trades
the refresh token for a new pair as the access token nears expiry. Only hashes are stored.
"""
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from ..users import User
from .jwt_utils import create_access_token

LOGIN_CODE_TTL_SECONDS = 60


@dataclass(frozen=True)
class AppTokens:
    access_token: str
    expires_in: int
    refresh_token: str


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AppTokenRepository:
    """`AuthCode#{hash}` items expire in a minute; `RefreshToken#{app}` sits under the user's key."""

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def put_login_code(self, code_hash: str, email: str, app: str, expires_at: int) -> None:
        self.table.put_item(Item={
            "pk": f"AuthCode#{code_hash}", "sk": "AuthCode#Metadata",
            "email": email, "app": app, "expires_at": expires_at, "ttl": expires_at,
        })

    def take_login_code(self, code_hash: str) -> Optional[dict[str, Any]]:
        """Delete and return the code, so it can only ever be redeemed once."""
        try:
            response = self.table.delete_item(
                Key={"pk": f"AuthCode#{code_hash}", "sk": "AuthCode#Metadata"},
                ConditionExpression="attribute_exists(pk)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return response["Attributes"]

    def put_refresh_token(self, email: str, app: str, token_hash: str, expires_at: int) -> None:
        self.table.put_item(Item={
            "pk": f"User#{email}", "sk": f"RefreshToken#{app}",
            "token_hash": token_hash, "expires_at": expires_at, "ttl": expires_at,
        })

    def get_refresh_token(self, email: str, app: str) -> Optional[dict[str, Any]]:
        return self.table.get_item(Key={"pk": f"User#{email}", "sk": f"RefreshToken#{app}"}).get("Item")

    def replace_refresh_token(self, email: str, app: str, old_hash: str, new_hash: str, expires_at: int) -> bool:
        """Swap the token only if it is still the one presented, so a token rotates exactly once."""
        try:
            self.table.update_item(
                Key={"pk": f"User#{email}", "sk": f"RefreshToken#{app}"},
                UpdateExpression="SET token_hash = :new, expires_at = :expires, #ttl = :expires",
                ConditionExpression="token_hash = :old",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":new": new_hash, ":old": old_hash, ":expires": expires_at},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def delete_refresh_token(self, email: str, app: str) -> None:
        self.table.delete_item(Key={"pk": f"User#{email}", "sk": f"RefreshToken#{app}"})


repository = AppTokenRepository()


def create_login_code(email: str, app: str) -> str:
    code = secrets.token_urlsafe(32)
    repository.put_login_code(_hash(code), email, app, int(time.time()) + LOGIN_CODE_TTL_SECONDS)
    return code


def redeem_login_code(code: str, app: str) -> Optional[str]:
    """The email the code was issued to, if it is unused, unexpired and was issued for this app."""
    item = repository.take_login_code(_hash(code))
    if item is None or item["app"] != app or int(item["expires_at"]) < time.time():
        return None
    return str(item["email"])


def issue_tokens(user: User, app: str) -> AppTokens:
    """A fresh pair; any earlier refresh token for this user and app stops working."""
    refresh_token = secrets.token_urlsafe(32)
    repository.put_refresh_token(user.email, app, _hash(refresh_token), _refresh_expiry())
    return _tokens(user, refresh_token)


def refresh_tokens(user: User, app: str, refresh_token: str) -> Optional[AppTokens]:
    stored = repository.get_refresh_token(user.email, app)
    if stored is None or int(stored["expires_at"]) < time.time():
        return None
    if not secrets.compare_digest(str(stored["token_hash"]), _hash(refresh_token)):
        return None

    rotated = secrets.token_urlsafe(32)
    if not repository.replace_refresh_token(user.email, app, str(stored["token_hash"]), _hash(rotated), _refresh_expiry()):
        return None
    return _tokens(user, rotated)


def revoke_tokens(email: str, app: str) -> None:
    repository.delete_refresh_token(email, app)


def _refresh_expiry() -> int:
    return int(time.time()) + settings.auth_refresh_token_days * 24 * 3600


def _tokens(user: User, refresh_token: str) -> AppTokens:
    lifetime = timedelta(minutes=settings.auth_app_access_token_minutes)
    return AppTokens(create_access_token(user, lifetime), int(lifetime.total_seconds()), refresh_token)
