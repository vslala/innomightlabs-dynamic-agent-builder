from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from ..config import settings
from ..users import User, UserRepository
from .google_oauth import GoogleOAuth
from .jwt_utils import create_access_token, get_current_user

import logging


log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

google_oauth = GoogleOAuth()
user_repository = UserRepository()


@router.get("/google")
async def login_with_google():
    """Redirect user to Google OAuth consent screen."""
    authorization_url, state = google_oauth.get_authorization_url()
    # In production, store state in session/cookie for validation
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def oauth_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Handle OAuth callback from Google."""
    if error:
        # Redirect to frontend with error
        frontend_error_url = f"{settings.frontend_url}/login?error={error}"
        return RedirectResponse(url=frontend_error_url)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        # Exchange code for tokens
        tokens = await google_oauth.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        # Get user info from Google
        user_info = await google_oauth.get_user_info(access_token)

        email = user_info.get("email")
        name = user_info.get("name")
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
        # Redirect to frontend with error
        frontend_error_url = f"{settings.frontend_url}/login?error=auth_failed"
        return RedirectResponse(url=frontend_error_url)


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
