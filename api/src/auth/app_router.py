"""Token endpoints for the backends of apps that share this login.

Authenticated with the app's own credentials (HTTP Basic: app name and its AUTH_APP_SECRETS entry),
not with a user's JWT, so these paths are public to AuthMiddleware.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from ..config import settings
from ..users import User, UserRepository
from ..users.models import UserStatus
from . import app_tokens

router = APIRouter(prefix="/auth", tags=["auth-apps"])
basic = HTTPBasic(auto_error=False)

user_repository = UserRepository()


class TokenRequest(BaseModel):
    code: str


class RefreshRequest(BaseModel):
    email: str
    refresh_token: str


class RevokeRequest(BaseModel):
    email: str


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    refresh_token: str
    email: str


def authenticated_app(credentials: HTTPBasicCredentials | None = Depends(basic)) -> str:
    secret = settings.auth_app_secrets.get(credentials.username) if credentials else None
    if not credentials or not secret or not secrets.compare_digest(credentials.password.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="invalid app credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _active_user(email: str | None) -> User:
    user = user_repository.get_by_email(email) if email else None
    if user is None or user.status in (UserStatus.INACTIVE.value, UserStatus.PENDING_DELETION.value):
        raise HTTPException(status_code=401, detail="invalid_grant")
    return user


def _response(user: User, tokens: app_tokens.AppTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token, expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token, email=user.email,
    )


@router.post("/token", response_model=TokenResponse)
async def exchange_login_code(body: TokenRequest, app: str = Depends(authenticated_app)) -> TokenResponse:
    """Redeem the one-time code the login redirect carried for an access and refresh token."""
    user = _active_user(app_tokens.redeem_login_code(body.code, app))
    return _response(user, app_tokens.issue_tokens(user, app))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, app: str = Depends(authenticated_app)) -> TokenResponse:
    """Trade a refresh token for a new access token and a rotated refresh token."""
    user = _active_user(body.email)
    tokens = app_tokens.refresh_tokens(user, app, body.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="invalid_grant")
    return _response(user, tokens)


@router.post("/revoke", status_code=204)
async def revoke(body: RevokeRequest, app: str = Depends(authenticated_app)) -> Response:
    """Forget the user's refresh token for this app, for example on logout."""
    app_tokens.revoke_tokens(body.email, app)
    return Response(status_code=204)
