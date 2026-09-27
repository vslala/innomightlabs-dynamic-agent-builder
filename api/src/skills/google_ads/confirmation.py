"""Tokens that tie an applied change to the exact change that was previewed.

A preview returns a token over the operations it validated; apply rebuilds the
operations from the same arguments and only proceeds if they still match. The
token is Fernet-encrypted, which also authenticates it, so nothing is stored.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from src.crypto import decrypt, encrypt

TOKEN_TTL_SECONDS = 15 * 60


def sign(scope: str, customer_id: str, operations: list[dict[str, Any]], ttl: int = TOKEN_TTL_SECONDS) -> str:
    claim = {"scope": scope, "customer": customer_id, "digest": _digest(operations), "expires": int(time.time()) + ttl}
    return encrypt(json.dumps(claim, sort_keys=True))


def verify(token: str | None, scope: str, customer_id: str, operations: list[dict[str, Any]]) -> None:
    if not token:
        raise ValueError("Applying a change needs the confirmation_token from its preview. Run the action with mode=preview first.")
    try:
        claim = json.loads(decrypt(token))
    except Exception as exc:
        raise ValueError("The confirmation_token is not valid. Run the action with mode=preview again.") from exc

    if int(claim.get("expires", 0)) < time.time():
        raise ValueError("The confirmation_token has expired. Run the action with mode=preview again.")
    if claim.get("scope") != scope or claim.get("customer") != customer_id or claim.get("digest") != _digest(operations):
        raise ValueError(
            "These arguments differ from the previewed change. Preview the change again, show it to the user, and apply that one."
        )


def _digest(operations: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(operations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
