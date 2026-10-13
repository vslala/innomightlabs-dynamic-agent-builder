"""How many images the public surfaces accept: per widget visitor and key, and per API key.

Guests and signed-in widget visitors share the limits. Dashboard members have none of their own: their sends
count against the account's subscription like any message.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from src.config import settings
from src.rate_limits.limiter import RateLimiter
from src.rate_limits.policy import RateLimitDecision, RateLimitPolicy

_HOUR = 3600
_DAY = 86400
LIMITED = {"code": "image_upload_limited", "message": "Too many images. Try again in a moment."}

#: A policy and the subject it counts.
Limit = tuple[RateLimitPolicy, str]


def widget_upload_limits(*, visitor_id: str, key_id: str) -> list[Limit]:
    """The visitor's own uploads, then every upload through the widget key."""
    return [
        (
            RateLimitPolicy.sliding_window(
                "WIDGET_IMAGE_UPLOADS", limit=settings.widget_image_uploads_per_visitor_hour, seconds=_HOUR,
                fail_open=False,
            ),
            visitor_id,
        ),
        (
            RateLimitPolicy.fixed_window(
                "WIDGET_IMAGE_UPLOADS_KEY_DAILY", limit=settings.widget_image_uploads_per_key_day, seconds=_DAY,
                fail_open=False,
            ),
            key_id,
        ),
    ]


def api_upload_limits(*, key_id: str) -> list[Limit]:
    return [
        (
            RateLimitPolicy.fixed_window(
                "API_IMAGE_UPLOADS_KEY_DAILY", limit=settings.api_image_uploads_per_key_day, seconds=_DAY,
                fail_open=False,
            ),
            key_id,
        )
    ]


@contextmanager
def image_upload_slot(limits: list[Limit]) -> Iterator[None]:
    """Count one upload against each limit, and give the slots back if the upload fails.

    Fails closed: uploads spend the owner's money once an agent reads them.
    """
    taken: list[tuple[RateLimiter, RateLimitDecision]] = []

    def release() -> None:
        for limiter, decision in taken:
            limiter.release(decision)

    for policy, subject in limits:
        limiter = RateLimiter(policy)
        decision = limiter.acquire(subject)
        if not decision.allowed:
            release()
            retry_after = decision.retry_after_seconds
            raise HTTPException(429, detail=LIMITED, headers={"Retry-After": str(retry_after)} if retry_after else None)
        taken.append((limiter, decision))
    try:
        yield
    except BaseException:
        release()
        raise
