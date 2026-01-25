from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import hashlib
import secrets
import time

from ..config import settings
from ..users import User, UserRepository
from .oauth_providers import CognitoOAuthProvider, GoogleOAuthProvider, OAuthProvider
from .jwt_utils import create_access_token, get_current_user

import logging


log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

user_repository = UserRepository()


def _get_provider(provider_name: str) -> OAuthProvider:
    if provider_name == "google":
        if not settings.is_google_oauth_configured():
            raise HTTPException(status_code=500, detail="Google OAuth is not configured")
        return GoogleOAuthProvider()
    if provider_name == "cognito":
        missing = []
        if not settings.cognito_domain:
            missing.append("COGNITO_DOMAIN")
        if not settings.cognito_client_id:
            missing.append("COGNITO_CLIENT_ID")
        if not settings.cognito_client_secret:
            missing.append("COGNITO_CLIENT_SECRET")
        if missing:
            raise HTTPException(status_code=500, detail=f"Cognito is not configured: {', '.join(missing)}")
        return CognitoOAuthProvider()
    raise HTTPException(status_code=404, detail="Unknown auth provider")


def _redirect_auth_error(error: str) -> RedirectResponse:
    frontend_error_url = f"{settings.frontend_url}/login?error={error}"
    return RedirectResponse(url=frontend_error_url)


@router.get("/google")
async def login_with_google():
    """Redirect user to Google OAuth consent screen."""
    provider = _get_provider("google")
    authorization_url, _state = provider.get_authorization_url()
    return RedirectResponse(url=authorization_url)


@router.get("/cognito")
async def login_with_cognito():
    """Redirect user to Cognito Hosted UI."""
    provider = _get_provider("cognito")
    authorization_url, _state = provider.get_authorization_url()
    return RedirectResponse(url=authorization_url)


async def _oauth_callback(
    provider_name: str,
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from an external provider."""
    if error:
        return _redirect_auth_error(error)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        provider = _get_provider(provider_name)
        tokens = await provider.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        user_info = await provider.get_user_info(access_token)

        email = user_info.get("email")
        name = user_info.get("name") or user_info.get("preferred_username")
        picture = user_info.get("picture")

        if not email:
            raise HTTPException(status_code=400, detail="Failed to get user email")

        # Create or update user in DynamoDB
        user = User(
            email=email,
            name=name or email.split("@")[0],
            picture=picture,
            refresh_token=refresh_token,
        )
        user = user_repository.create_or_update(user)

        # Generate JWT token for our app
        jwt_token = create_access_token(user)

        # Redirect to frontend with token
        redirect_params = urlencode({"token": jwt_token})
        redirect_url = f"{settings.frontend_url}/login-success?{redirect_params}"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        log.error(f"OAuth callback error ({provider_name}): {e}", exc_info=True)
        return _redirect_auth_error("auth_failed")


@router.get("/callback")
async def oauth_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from Google (legacy route)."""
    return await _oauth_callback("google", code=code, error=error, state=state)


@router.get("/callback/google")
async def oauth_callback_google(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from Google."""
    return await _oauth_callback("google", code=code, error=error, state=state)


@router.get("/callback/cognito")
async def oauth_callback_cognito(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from Cognito."""
    return await _oauth_callback("cognito", code=code, error=error, state=state)


@router.get("/me")
async def get_current_user_info(
    user: User = Depends(get_current_user),
):
    """Get current authenticated user info."""
    return {
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }


class LocalSignupRequest(BaseModel):
    username: str
    password: str


class LocalLoginRequest(BaseModel):
    username: str
    password: str


class LocalAuthResponse(BaseModel):
    token: str
    email: str
    name: str


def _hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    """Hash password using PBKDF2-SHA256."""
    if salt is None:
        salt = secrets.token_bytes(32)

    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return hashed.hex(), salt.hex()


def _verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verify password against stored hash."""
    salt_bytes = bytes.fromhex(salt)
    computed_hash, _ = _hash_password(password, salt_bytes)
    return computed_hash == hashed_password


@router.post("/local/signup", response_model=LocalAuthResponse)
async def local_signup(payload: LocalSignupRequest):
    """
    Dev-only endpoint for local testing with username/password.

    Creates a user with email format: {username}@example.com
    Only available when ENVIRONMENT is 'dev' or 'local'.
    """
    if settings.environment not in ["dev", "local"]:
        raise HTTPException(
            status_code=403,
            detail="Local signup is only available in development environment"
        )

    # Create email from username using example.com (RFC 2606 reserved domain)
    email = f"{payload.username}@example.com"

    # Check if user already exists
    existing_user = user_repository.get_by_email(email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already taken"
        )

    # Hash password
    hashed_password, salt = _hash_password(payload.password)

    # Calculate TTL: 7 days from now (Unix timestamp in seconds)
    ttl_timestamp = int(time.time() + (7 * 24 * 60 * 60))

    # Create user in DynamoDB with TTL for auto-expiration
    user = User(
        email=email,
        name=payload.username,
        picture=None,
        refresh_token=None,
        password_hash=hashed_password,
        password_salt=salt,
        ttl=ttl_timestamp,
    )

    user = user_repository.create_or_update(user)

    # Generate JWT token
    jwt_token = create_access_token(user)

    return LocalAuthResponse(
        token=jwt_token,
        email=user.email,
        name=user.name
    )


@router.post("/local/login", response_model=LocalAuthResponse)
async def local_login(payload: LocalLoginRequest):
    """
    Dev-only endpoint for logging in with username/password.

    Only available when ENVIRONMENT is 'dev' or 'local'.
    """
    if settings.environment not in ["dev", "local"]:
        raise HTTPException(
            status_code=403,
            detail="Local login is only available in development environment"
        )

    # Create email from username
    email = f"{payload.username}@example.com"

    # Get user from database
    user = user_repository.get_by_email(email)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Check if user has password (is a local dev user)
    if not user.password_hash or not user.password_salt:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Verify password
    if not _verify_password(payload.password, user.password_hash, user.password_salt):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    # Generate JWT token
    jwt_token = create_access_token(user)

    return LocalAuthResponse(
        token=jwt_token,
        email=user.email,
        name=user.name
    )
