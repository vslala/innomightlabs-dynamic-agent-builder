"""What a social network is to the rest of the platform. Everything that varies by network lives behind this
protocol, so a new network is one file in this folder and one line in `networks/__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class ConnectError(Exception):
    """Connecting an account failed. The message is safe to log: it never holds a token or a secret."""


@dataclass(frozen=True)
class ConnectedProfile:
    """One postable identity a sign-in granted: a member, a Page, a professional account."""

    external_id: str
    handle: str
    display_name: str
    avatar_url: str | None
    #: Opaque to everything but the strategy that wrote it; stored encrypted
    credentials: dict[str, Any]
    scopes: str = ""
    expires_at: datetime | None = None


class SocialNetwork(Protocol):
    key: str
    display_name: str
    #: A brand mark key the dashboard knows (`spa/src/assets/connectors/<icon>.svg`)
    icon: str
    #: Names its OAuth app in the environment: `SOCIAL_<APP>_CLIENT_ID` / `_CLIENT_SECRET` (see `settings.social_app`)
    app: str

    def configured(self) -> bool:
        """Its OAuth app is registered: the network is offered only then."""
        ...

    def authorize_url(self, state: str, code_challenge: str) -> str:
        """Where to send the person to sign in. A network without PKCE ignores the challenge."""
        ...

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        """Exchange the sign-in's code for the identities it granted (usually one). Raises ConnectError."""
        ...

    async def revoke(self, credentials: dict[str, Any]) -> None:
        """Best effort: end the grant at the network when the account is disconnected."""
        ...
