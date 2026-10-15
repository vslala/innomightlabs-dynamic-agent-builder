"""One slot under several limits at once, for work that can fail: if it does, every slot is given back."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from src.rate_limits.limiter import RateLimiter
from src.rate_limits.policy import RateLimitDecision, RateLimitPolicy

#: A policy and the subject it counts.
Limit = tuple[RateLimitPolicy, str]


@contextmanager
def limit_slot(limits: list[Limit], *, refusal: dict[str, str]) -> Iterator[None]:
    """Count one use against each limit; a 429 with `refusal` as its detail when any is spent."""
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
            raise HTTPException(429, detail=refusal, headers={"Retry-After": str(retry_after)} if retry_after else None)
        taken.append((limiter, decision))
    try:
        yield
    except BaseException:
        release()
        raise
