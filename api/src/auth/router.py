from urllib.parse import urlencode, urlparse, parse_qsl
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import hashlib
import secrets
import time
from datetime import datetime, timezone

from ..config import settings
from ..users import User, UserRepository
from ..settings.models import ProviderSettings
from ..settings.repository import ProviderSettingsRepository
from .oauth_providers import CognitoOAuthProvider, GoogleOAuthProvider, OAuthProvider
from .openai_oauth import (
    OpenAIOAuthError,
    build_authorization_url,
    build_credentials_from_auth_code,
    decode_state_session,
    encode_state_session,
    generate_pkce_bundle,
    generate_code_challenge,
    OpenAIOAuthState,
    save_credentials,
)
from .jwt_utils import create_access_token, get_current_user
from ..email import send_welcome_email_safe

import logging


log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

user_repository = UserRepository()
provider_settings_repository = ProviderSettingsRepository()
OPENAI_PKCE_TTL_SECONDS = 600


class OpenAIStartRequest(BaseModel):
    return_to: str | None = None


class OpenAIStartResponse(BaseModel):
    authorize_url: str


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current_query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current_query.update(params)
    query = urlencode(current_query)
    return parsed._replace(query=query).geturl()


def _openai_settings_redirect(status_value: str, return_to: str | None = None) -> RedirectResponse:
    target = return_to or f"{settings.frontend_url}/dashboard/settings"
    return RedirectResponse(url=_append_query_params(target, {"openai_oauth": status_value}))


def _extract_openai_state_session(state: str | None) -> tuple[OpenAIOAuthState | None, str]:
    return_to = f"{settings.frontend_url}/dashboard/settings"
    session = decode_state_session(state)
    if not session:
        return None, return_to
    return_to = session.return_to or return_to
    return session, return_to


async def _handle_openai_oauth_callback(
    code: str | None,
    error: str | None,
    state: str | None,
) -> RedirectResponse:
    oauth_session, return_to = _extract_openai_state_session(state)

    try:
        if error or not oauth_session:
            return _openai_settings_redirect("error", return_to=return_to)

        if oauth_session.is_expired():
            return _openai_settings_redirect("error", return_to=return_to)

        if not code:
            return _openai_settings_redirect("error", return_to=return_to)

        credentials = await build_credentials_from_auth_code(
            code=code,
            code_verifier=oauth_session.code_verifier,
        )

        provider_settings = ProviderSettings(
            user_email=oauth_session.user_email,
            provider_name="OpenAI",
            encrypted_credentials="",
            auth_type="oauth",
        )
        save_credentials(provider_settings, provider_settings_repository, credentials)
        return _openai_settings_redirect("success", return_to=return_to)

    except OpenAIOAuthError as e:
        log.error(f"OpenAI OAuth callback error: {e}", exc_info=True)
        return _openai_settings_redirect("error", return_to=return_to)
    except Exception as e:
        log.error(f"Unexpected OpenAI OAuth callback error: {e}", exc_info=True)
        return _openai_settings_redirect("error", return_to=return_to)


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


@router.post("/openai/start", response_model=OpenAIStartResponse)
async def start_openai_oauth(request: Request, body: OpenAIStartRequest | None = None):
    """
    Start backend-owned OpenAI OAuth PKCE flow.
    """
    if not settings.is_openai_oauth_configured():
        raise HTTPException(status_code=500, detail="OpenAI OAuth is not configured")

    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Unauthorized")

    nonce, code_verifier = generate_pkce_bundle()
    code_challenge = generate_code_challenge(code_verifier)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    session = OpenAIOAuthState(
        nonce=nonce,
        code_verifier=code_verifier,
        user_email=user_email,
        return_to=(body.return_to if body and body.return_to else f"{settings.frontend_url}/dashboard/settings"),
        expires_at=now_ts + OPENAI_PKCE_TTL_SECONDS,
    )
    state = encode_state_session(session)
    authorize_url = build_authorization_url(state=state, code_challenge=code_challenge)
    return OpenAIStartResponse(authorize_url=authorize_url)


@router.get("/openai")
async def openai_oauth_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """
    OpenAI OAuth callback endpoint.
    """
    return await _handle_openai_oauth_callback(code=code, error=error, state=state)


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

        # Check if user exists (for welcome email)
        existing_user = user_repository.get_by_email(email)
        is_new_user = existing_user is None

        # Create or update user in DynamoDB
        user = User(
            email=email,
            name=name or email.split("@")[0],
            picture=picture,
            refresh_token=refresh_token,
        )
        user = user_repository.create_or_update(user)

        # Send welcome email for new users
        if is_new_user:
            await send_welcome_email_safe(email)

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
    _request: Request,
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from Google (legacy route) or OpenAI (state payload flow)."""
    state_session, _ = _extract_openai_state_session(state)
    if state_session:
        return await _handle_openai_oauth_callback(code=code, error=error, state=state)
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
