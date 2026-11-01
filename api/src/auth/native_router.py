"""Token endpoints for the store apps (iOS and Android), which are public clients.

An app binary can't keep a secret, so instead of HTTP Basic the app proves it started the login with the
PKCE verifier for the challenge it sent (RFC 7636), and later proves possession of its device's refresh
token. The paths are public to AuthMiddleware, and rate limited per client address.
See docs/LLD-mobile-ready-app.md, section 2.
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..identity import IdentityRepository
from ..rate_limits.limiter import RateLimitPolicy, RateLimiter
from . import app_tokens
from .app_router import _active
from .apps import native_app_enabled

router = APIRouter(prefix="/auth/native", tags=["auth-native"])

identity_repository = IdentityRepository()

#: Codes are single use and verifiers are 256-bit, so this only stops a client hammering the endpoints.
NATIVE_TOKEN_RATE_LIMIT = RateLimitPolicy.fixed_window("NATIVE_AUTH", limit=30, seconds=60)

# A device id is a random UUID the app made once: an opaque key, never a hardware identifier.
DeviceId = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class NativeTokenRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    code_verifier: str = Field(min_length=43, max_length=128)
    device_id: str = DeviceId


class NativeRefreshRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    device_id: str = DeviceId
    refresh_token: str = Field(min_length=1, max_length=256)


class NativeTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str


def _guard(request: Request) -> None:
    if not native_app_enabled():
        raise HTTPException(status_code=404, detail="Native sign-in is not enabled")
    client_ip = request.client.host if request.client else "unknown"
    if not RateLimiter(NATIVE_TOKEN_RATE_LIMIT).acquire(client_ip).allowed:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in a minute.")


def _invalid_grant() -> HTTPException:
    return HTTPException(status_code=401, detail="invalid_grant")


@router.post("/token", response_model=NativeTokenResponse)
async def exchange_native_login_code(body: NativeTokenRequest, request: Request) -> NativeTokenResponse:
    """Redeem the code the `auth` app link carried, with the verifier, for this device's tokens."""
    _guard(request)
    user_id = app_tokens.redeem_native_login_code(body.code, body.code_verifier)
    user = _active(identity_repository.get(user_id) if user_id else None)
    tokens = app_tokens.issue_native_tokens(user, body.device_id)
    return NativeTokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in, user_id=user.user_id,
    )


@router.post("/refresh", response_model=NativeTokenResponse)
async def refresh_native_tokens(body: NativeRefreshRequest, request: Request) -> NativeTokenResponse:
    """A new access token and a rotated refresh token. Expired, reused or inactive: invalid_grant."""
    _guard(request)
    user = _active(identity_repository.get(body.user_id))
    tokens = app_tokens.refresh_native_tokens(user, body.device_id, body.refresh_token)
    if tokens is None:
        raise _invalid_grant()
    return NativeTokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in, user_id=user.user_id,
    )


@router.post("/revoke", status_code=204)
async def revoke_native_tokens(body: NativeRefreshRequest, request: Request) -> Response:
    """Sign this device out. Always 204, so the response says nothing about which tokens exist."""
    _guard(request)
    app_tokens.revoke_native_tokens(body.user_id, body.device_id, body.refresh_token)
    return Response(status_code=204)
