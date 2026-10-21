"""What a social network is to the rest of the platform. Everything that varies by network lives behind this
protocol, so a new network is one file in this folder and one line in `networks/__init__.py`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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


class PublishErrorKind(str, Enum):
    #: The network refused the token: the person has to connect again.
    AUTH = "auth"
    #: The network refused this post (too long, not allowed). Retrying the same post won't help.
    REJECTED = "rejected"
    RATE_LIMITED = "rate_limited"
    #: Failed before anything was created, so trying again is safe.
    TRANSIENT = "transient"
    #: The create call may or may not have gone through (timeout, 5xx). Never retried: it could post twice.
    UNCERTAIN = "uncertain"


class PublishError(Exception):
    """Posting failed. The message is safe to show the person and the agent: it never holds a token."""

    def __init__(self, kind: PublishErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class NetworkLimits:
    """What a network accepts in one post. The agent is told these before it offers to post."""

    max_text: int
    #: How many images one post takes; 0 is a text-only network
    max_images: int = 0
    requires_image: bool = False
    #: The longest side and the file size a post's image may have; `media.prepare` fits each image to them
    max_image_side: int = 4096
    max_image_bytes: int = 8 * 1024 * 1024


@dataclass(frozen=True)
class PreparedImage:
    """An image fitted to one network's limits."""

    data: bytes
    mime_type: str
    alt_text: str = ""


@dataclass(frozen=True)
class PreparedPost:
    text: str
    images: tuple[PreparedImage, ...] = ()


@dataclass(frozen=True)
class PublishedPost:
    external_id: str
    url: str | None = None


class SocialNetwork(Protocol):
    key: str
    display_name: str
    #: A brand mark key the dashboard knows (`spa/src/assets/connectors/<icon>.svg`)
    icon: str
    #: Names its OAuth app in the environment: `SOCIAL_<APP>_CLIENT_ID` / `_CLIENT_SECRET` (see `settings.social_app`)
    app: str
    limits: NetworkLimits

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

    async def publish(self, credentials: dict[str, Any], post: PreparedPost) -> PublishedPost:
        """Create the post. Raises PublishError, classified so the publisher knows whether a retry is safe."""
        ...
