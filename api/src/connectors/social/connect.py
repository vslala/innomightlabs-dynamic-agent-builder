"""Connecting a social account. The browser leaves for the network, comes back to the public callback, and the SPA
finishes the connection signed in, through `POST /connectors/oauth/complete` (see src/auth/oauth_handoff.py)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone

from pydantic import BaseModel, ValidationError

from src.connectors.social.models import SocialAccount
from src.connectors.social.networks import network_for
from src.connectors.social.networks.base import ConnectError
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import decrypt, encrypt
from src.settings.access import may_manage_settings

log = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600


class SocialOAuthState(BaseModel):
    """Everything the callback needs, sealed in the `state` the network returns; nothing is stored on the server."""

    nonce: str
    network: str
    account_id: str
    user_id: str
    user_email: str
    #: For networks that do PKCE; the others ignore the challenge made from it
    code_verifier: str
    return_to: str
    expires_at: int

    def is_expired(self) -> bool:
        return int(datetime.now(timezone.utc).timestamp()) > self.expires_at


def decode_state(state: str | None) -> SocialOAuthState | None:
    if not state:
        return None
    try:
        return SocialOAuthState.model_validate_json(decrypt(state))
    except (ValidationError, Exception):
        return None


def authorize_url_for(network_key: str, *, account_id: str, user_id: str, user_email: str, return_to: str) -> str:
    """Where to send the person to sign in to `network_key`. Raises ValueError for a network that isn't offered."""
    network = network_for(network_key)
    if not network.configured():
        raise ValueError(f"{network.display_name} is not set up on this server")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = SocialOAuthState(
        nonce=secrets.token_urlsafe(16),
        network=network.key,
        account_id=account_id,
        user_id=user_id,
        user_email=user_email,
        code_verifier=verifier,
        return_to=return_to,
        expires_at=int(datetime.now(timezone.utc).timestamp()) + STATE_TTL_SECONDS,
    )
    return network.authorize_url(encrypt(state.model_dump_json()), challenge)


async def complete_social_oauth(
    *, state: str | None, code: str | None, error: str | None, user_email: str, user_id: str
) -> dict[str, str]:
    """Save the accounts a sign-in granted, if the signed-in user started it and may still manage the account's
    settings. Returns the page's result parameters."""
    session = decode_state(state)
    if not session or session.is_expired() or session.user_email != user_email:
        return {"social_oauth": "error", "reason": "invalid_state"}
    result = {"social_oauth": "error", "network": session.network}
    if not may_manage_settings(user_id, session.account_id):
        return {**result, "reason": "not_allowed"}
    if error:
        return {**result, "reason": "cancelled"}
    if not code:
        return {**result, "reason": "missing_code"}

    network = network_for(session.network)
    try:
        profiles = await network.complete(code, session.code_verifier)
    except ConnectError as failure:
        log.error("Connecting %s failed: %s", network.key, failure)
        return {**result, "reason": "callback_failed"}
    except Exception:
        log.exception("Connecting %s failed", network.key)
        return {**result, "reason": "callback_failed"}

    repository = SocialAccountRepository()
    saved = [
        repository.connect(SocialAccount(
            account_id=session.account_id,
            network=network.key,
            external_id=profile.external_id,
            handle=profile.handle,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
            encrypted_credentials=encrypt(json.dumps(profile.credentials)),
            scopes=profile.scopes,
            token_expires_at=profile.expires_at,
            connected_by=user_id,
        ))
        for profile in profiles
    ]
    return {
        "social_oauth": "success",
        "network": network.key,
        "social_account_ids": ",".join(account.social_account_id for account in saved),
    }
