"""What a rate limit is, and what checking one decides. See `limiter.py` for how they're used."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RateLimitAlgorithm(str, Enum):
    #: One request, then nothing until `window_seconds` have passed.
    COOLDOWN = "cooldown"
    #: Up to `limit` per calendar window. Cheapest; allows up to 2x `limit` across a window edge.
    FIXED_WINDOW = "fixed_window"
    #: Up to `limit` in any rolling window, estimated from the current and previous windows.
    SLIDING_WINDOW = "sliding_window"


@dataclass(frozen=True)
class RateLimitPolicy:
    #: Names the limit in storage keys, e.g. "CONTACT" or "GUEST_MESSAGES". Keep it stable.
    scope: str
    algorithm: RateLimitAlgorithm
    limit: int
    window_seconds: int
    #: When the store can't be reached: allow the request (True) or refuse it (False).
    fail_open: bool = True

    def __post_init__(self) -> None:
        if not self.scope or "#" in self.scope:
            raise ValueError("scope must be non-empty and contain no '#'")
        if self.limit < 1 or self.window_seconds < 1:
            raise ValueError("limit and window_seconds must be at least 1")

    @classmethod
    def cooldown(cls, scope: str, *, seconds: int, fail_open: bool = True) -> RateLimitPolicy:
        return cls(scope, RateLimitAlgorithm.COOLDOWN, 1, seconds, fail_open)

    @classmethod
    def fixed_window(cls, scope: str, *, limit: int, seconds: int, fail_open: bool = True) -> RateLimitPolicy:
        return cls(scope, RateLimitAlgorithm.FIXED_WINDOW, limit, seconds, fail_open)

    @classmethod
    def sliding_window(cls, scope: str, *, limit: int, seconds: int, fail_open: bool = True) -> RateLimitPolicy:
        return cls(scope, RateLimitAlgorithm.SLIDING_WINDOW, limit, seconds, fail_open)


@dataclass(frozen=True)
class RateLimitSlot:
    """The capacity one allowed request took, so `release` can hand back exactly that."""

    pk: str
    sk: str
    #: The cooldown's expiry, so a release can't remove a newer holder's cooldown.
    expires_at: int | None = None


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    #: Seconds until a request would be allowed; None when allowed, or when the store was unreachable.
    retry_after_seconds: int | None = None
    #: Requests still allowed in the window after this one, when the algorithm can tell.
    remaining: int | None = None
    slot: RateLimitSlot | None = None

    @classmethod
    def allow(cls, slot: RateLimitSlot, remaining: int | None) -> RateLimitDecision:
        return cls(True, None, remaining, slot)

    @classmethod
    def deny(cls, retry_after_seconds: int) -> RateLimitDecision:
        return cls(False, max(1, retry_after_seconds))
