import secrets
from typing import Any, Optional, Protocol, cast
from urllib.parse import urlencode

import httpx

from ..config import settings
from .google_oauth import GoogleOAuth
import logging

log = logging.getLogger(__name__)

class OAuthProvider(Protocol):
    name: str

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        ...

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        ...

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        ...


class GoogleOAuthProvider:
    name = "google"

    def __init__(self) -> None:
        self.client = GoogleOAuth()

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        return self.client.get_authorization_url(state=state, redirect_uri=settings.google_redirect_uri)

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        return await self.client.exchange_code_for_tokens(code, redirect_uri=settings.google_redirect_uri)

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        return await self.client.get_user_info(access_token)


class CognitoOAuthProvider:
    name = "cognito"

    AUTHORIZATION_PATH = "/oauth2/authorize"
    TOKEN_PATH = "/oauth2/token"
    USERINFO_PATH = "/oauth2/userInfo"

    SCOPES = ["openid", "email", "profile"]

    def __init__(self) -> None:
        self.domain = settings.cognito_domain.rstrip("/")
        self.client_id = settings.cognito_client_id
        self.client_secret = settings.cognito_client_secret
        self.redirect_uri = settings.cognito_redirect_uri

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
        }
        url = f"{self.domain}{self.AUTHORIZATION_PATH}?{urlencode(params)}"
        log.info(f"Redirecting to cognito: {url}")
        return url, state

    async def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.domain}{self.TOKEN_PATH}",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.domain}{self.USERINFO_PATH}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
