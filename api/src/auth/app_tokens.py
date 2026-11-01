"""Login codes and refresh tokens for the apps that share this login (see auth/apps.py).

An app's backend redeems a one-time login code for an access token and a refresh token, then trades
the refresh token for a new pair as the access token nears expiry. Only hashes are stored.

The store apps (NATIVE_APP) redeem their code with a PKCE verifier instead of a secret, get owner access
tokens (the same audience as the web), and keep one refresh token per device, so signing in on a second
phone doesn't sign the first one out and each device can be revoked alone.
"""
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional, cast

from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from ..identity import Identity
from .apps import NATIVE_APP
from .jwt_utils import app_audience, create_access_token

LOGIN_CODE_TTL_SECONDS = 60


@dataclass(frozen=True)
class AppTokens:
    access_token: str
    expires_in: int
    refresh_token: str


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AppTokenRepository:
    """`AuthCode#{hash}` items expire in a minute; `RefreshToken#{app}` sits under the identity's key."""

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def put_login_code(
        self, code_hash: str, user_id: str, app: str, expires_at: int, code_challenge: str | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "pk": f"AuthCode#{code_hash}", "sk": "AuthCode#Metadata",
            "user_id": user_id, "app": app, "expires_at": expires_at, "ttl": expires_at,
        }
        if code_challenge is not None:
            item["code_challenge"] = code_challenge
        self.table.put_item(Item=item)

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
        return cast(dict[str, Any], response["Attributes"])

    def put_refresh_token(self, user_id: str, app: str, token_hash: str, expires_at: int) -> None:
        self.table.put_item(Item={
            "pk": f"Identity#{user_id}", "sk": f"RefreshToken#{app}",
            "token_hash": token_hash, "expires_at": expires_at, "ttl": expires_at,
        })

    def get_refresh_token(self, user_id: str, app: str) -> Optional[dict[str, Any]]:
        item = self.table.get_item(Key={"pk": f"Identity#{user_id}", "sk": f"RefreshToken#{app}"}).get("Item")
        return cast(Optional[dict[str, Any]], item)

    def replace_refresh_token(self, user_id: str, app: str, old_hash: str, new_hash: str, expires_at: int) -> bool:
        """Swap the token only if it is still the one presented, so a token rotates exactly once."""
        try:
            self.table.update_item(
                Key={"pk": f"Identity#{user_id}", "sk": f"RefreshToken#{app}"},
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

    def delete_refresh_token(self, user_id: str, app: str) -> None:
        self.table.delete_item(Key={"pk": f"Identity#{user_id}", "sk": f"RefreshToken#{app}"})


repository = AppTokenRepository()


def create_login_code(user_id: str, app: str, code_challenge: str | None = None) -> str:
    code = secrets.token_urlsafe(32)
    repository.put_login_code(_hash(code), user_id, app, int(time.time()) + LOGIN_CODE_TTL_SECONDS, code_challenge)
    return code


def redeem_login_code(code: str, app: str) -> Optional[str]:
    """The user_id the code was issued to, if it is unused, unexpired and was issued for this app."""
    item = repository.take_login_code(_hash(code))
    if item is None or item["app"] != app or int(item["expires_at"]) < time.time():
        return None
    return str(item["user_id"])


def redeem_native_login_code(code: str, code_verifier: str) -> Optional[str]:
    """The user_id behind a native login code, if it is unused, unexpired and the verifier matches its challenge."""
    item = repository.take_login_code(_hash(code))
    if item is None or item["app"] != NATIVE_APP or int(item["expires_at"]) < time.time():
        return None
    challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    if not secrets.compare_digest(challenge, str(item.get("code_challenge") or "")):
        return None
    return str(item["user_id"])


def _native_key(device_id: str) -> str:
    """The refresh token's sort key suffix: `RefreshToken#mobile#{device_id}`, one per device."""
    return f"{NATIVE_APP}#{device_id}"


def issue_native_tokens(user: Identity, device_id: str) -> AppTokens:
    """A fresh pair for this device; the person's other devices keep theirs."""
    refresh_token = secrets.token_urlsafe(32)
    repository.put_refresh_token(user.user_id, _native_key(device_id), _hash(refresh_token), _refresh_expiry())
    return _native_tokens(user, refresh_token)


def refresh_native_tokens(user: Identity, device_id: str, refresh_token: str) -> Optional[AppTokens]:
    rotated = _rotate(user.user_id, _native_key(device_id), refresh_token)
    return _native_tokens(user, rotated) if rotated else None


def revoke_native_tokens(user_id: str, device_id: str, refresh_token: str) -> None:
    """Forget this device's refresh token, if the caller holds it: possession is the proof, not a bearer."""
    stored = repository.get_refresh_token(user_id, _native_key(device_id))
    if stored is not None and secrets.compare_digest(str(stored["token_hash"]), _hash(refresh_token)):
        repository.delete_refresh_token(user_id, _native_key(device_id))


def issue_tokens(user: Identity, app: str) -> AppTokens:
    """A fresh pair; any earlier refresh token for this user and app stops working."""
    refresh_token = secrets.token_urlsafe(32)
    repository.put_refresh_token(user.user_id, app, _hash(refresh_token), _refresh_expiry())
    return _tokens(user, app, refresh_token)


def refresh_tokens(user: Identity, app: str, refresh_token: str) -> Optional[AppTokens]:
    rotated = _rotate(user.user_id, app, refresh_token)
    return _tokens(user, app, rotated) if rotated else None


def _rotate(user_id: str, key: str, refresh_token: str) -> Optional[str]:
    """A new refresh token in place of the one presented, if that one is current and unexpired; it rotates once."""
    stored = repository.get_refresh_token(user_id, key)
    if stored is None or int(stored["expires_at"]) < time.time():
        return None
    if not secrets.compare_digest(str(stored["token_hash"]), _hash(refresh_token)):
        return None

    rotated = secrets.token_urlsafe(32)
    if not repository.replace_refresh_token(user_id, key, str(stored["token_hash"]), _hash(rotated), _refresh_expiry()):
        return None
    return rotated


def revoke_tokens(user_id: str, app: str) -> None:
    repository.delete_refresh_token(user_id, app)


def _refresh_expiry() -> int:
    return int(time.time()) + settings.auth_refresh_token_days * 24 * 3600


def _native_tokens(user: Identity, refresh_token: str) -> AppTokens:
    """Owner-audience access, so every dashboard route accepts it with no middleware change."""
    lifetime = timedelta(minutes=settings.native_access_token_minutes)
    return AppTokens(create_access_token(user, lifetime), int(lifetime.total_seconds()), refresh_token)


def _tokens(user: Identity, app: str, refresh_token: str) -> AppTokens:
    lifetime = timedelta(minutes=settings.auth_app_access_token_minutes)
    access_token = create_access_token(user, lifetime, audience=app_audience(app))
    return AppTokens(access_token, int(lifetime.total_seconds()), refresh_token)
