"""Request rate limiting with a choice of algorithm.

A `RateLimitPolicy` names what is limited and how; `RateLimiter` applies it to one subject (an IP,
an email, a guest id) at a time. The algorithm is a strategy picked from `RATE_LIMIT_STRATEGIES`,
so a caller chooses behaviour by choosing a policy constructor and never branches on algorithm:

    CONTACT = RateLimitPolicy.cooldown("CONTACT", seconds=300)
    GUEST_MESSAGES = RateLimitPolicy.sliding_window("GUEST_MESSAGES", limit=30, seconds=3600)

    decision = RateLimiter(GUEST_MESSAGES).acquire(guest_id)
    if not decision.allowed:
        raise HTTPException(429, headers={"Retry-After": str(decision.retry_after_seconds)})

`acquire` consumes capacity atomically, so two concurrent requests cannot both take the last slot.
`release` hands it back when the work it guarded failed and should not count.

Expiry never depends on DynamoDB TTL deleting an item on time (TTL can lag by up to 48 hours):
every decision compares stored timestamps or window numbers with the clock, and `ttl` only cleans up.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable

from src.rate_limits.policy import RateLimitAlgorithm, RateLimitDecision, RateLimitPolicy
from src.rate_limits.store import DynamoRateLimitStore, RateLimitStore
from src.rate_limits.strategies import RATE_LIMIT_STRATEGIES, RateLimitStrategy

__all__ = ["RateLimitAlgorithm", "RateLimitDecision", "RateLimitPolicy", "RateLimiter", "strategy_for"]

log = logging.getLogger(__name__)


def strategy_for(algorithm: RateLimitAlgorithm) -> RateLimitStrategy:
    """The one place an algorithm is turned into its implementation."""
    for strategy in RATE_LIMIT_STRATEGIES:
        if strategy.algorithm == algorithm:
            return strategy
    raise ValueError(f"No rate limit strategy for {algorithm!r}")


class RateLimiter:
    def __init__(
        self,
        policy: RateLimitPolicy,
        store: RateLimitStore | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.policy = policy
        self.strategy = strategy_for(policy.algorithm)
        self.store = store or DynamoRateLimitStore()
        self.clock = clock

    def acquire(self, subject: str) -> RateLimitDecision:
        """Take one request's worth of capacity for `subject`, or say how long to wait."""
        try:
            return self.strategy.acquire(self.store, self._pk(subject), self.policy, int(self.clock()))
        except Exception:
            log.exception("Rate limit check failed for scope %s", self.policy.scope)
            return RateLimitDecision(allowed=self.policy.fail_open)

    def release(self, decision: RateLimitDecision) -> None:
        """Give back what an allowed `acquire` took, e.g. when the guarded work failed."""
        if not decision.allowed or decision.slot is None:
            return
        try:
            self.strategy.release(self.store, decision.slot)
        except Exception:
            log.exception("Rate limit release failed for scope %s", self.policy.scope)

    def _pk(self, subject: str) -> str:
        # Subjects are IPs and emails, so only a hash is ever stored.
        digest = hashlib.sha256(subject.encode()).hexdigest()[:16]
        return f"RATE_LIMIT#{self.policy.scope}#{digest}"
