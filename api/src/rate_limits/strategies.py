"""The rate limit algorithms. Each turns one `acquire` into store operations and a decision.

Counters only keep requests that were allowed: a refused request's increment is undone, so a
client that keeps retrying while blocked is let back in on schedule instead of extending its block.
"""

from __future__ import annotations

import math
from typing import Protocol

from src.rate_limits.policy import RateLimitAlgorithm, RateLimitDecision, RateLimitPolicy, RateLimitSlot
from src.rate_limits.store import RateLimitStore

COOLDOWN_SK = "COOLDOWN"
#: Counters outlive their window by this much before TTL may remove them.
COUNTER_TTL_MARGIN_SECONDS = 3600


class RateLimitStrategy(Protocol):
    algorithm: RateLimitAlgorithm

    def acquire(self, store: RateLimitStore, pk: str, policy: RateLimitPolicy, now: int) -> RateLimitDecision: ...

    def release(self, store: RateLimitStore, slot: RateLimitSlot) -> None: ...


def _window_sk(window_start: int) -> str:
    return f"WINDOW#{window_start}"


class CooldownStrategy:
    """One request per window, enforced by a lock that expires `window_seconds` after it was taken."""

    algorithm = RateLimitAlgorithm.COOLDOWN

    def acquire(self, store: RateLimitStore, pk: str, policy: RateLimitPolicy, now: int) -> RateLimitDecision:
        expires_at = now + policy.window_seconds
        if store.claim(pk, COOLDOWN_SK, now, expires_at):
            return RateLimitDecision.allow(RateLimitSlot(pk, COOLDOWN_SK, expires_at), remaining=0)
        held_until = store.claim_expiry(pk, COOLDOWN_SK)
        return RateLimitDecision.deny((held_until or now) - now)

    def release(self, store: RateLimitStore, slot: RateLimitSlot) -> None:
        if slot.expires_at is not None:
            store.release_claim(slot.pk, slot.sk, slot.expires_at)


class _CounterStrategy:
    """Shared by the window counters: count into the current window, undo when refused."""

    def release(self, store: RateLimitStore, slot: RateLimitSlot) -> None:
        store.add(slot.pk, slot.sk, -1, ttl=0)

    @staticmethod
    def _count(store: RateLimitStore, pk: str, window_start: int, ttl: int) -> int:
        return store.add(pk, _window_sk(window_start), 1, ttl)

    @staticmethod
    def _undo(store: RateLimitStore, pk: str, window_start: int) -> None:
        store.add(pk, _window_sk(window_start), -1, ttl=0)


class FixedWindowStrategy(_CounterStrategy):
    """Up to `limit` requests per calendar window, e.g. 10:00:00-10:59:59."""

    algorithm = RateLimitAlgorithm.FIXED_WINDOW

    def acquire(self, store: RateLimitStore, pk: str, policy: RateLimitPolicy, now: int) -> RateLimitDecision:
        size = policy.window_seconds
        start = now - now % size
        count = self._count(store, pk, start, ttl=start + size + COUNTER_TTL_MARGIN_SECONDS)
        if count <= policy.limit:
            return RateLimitDecision.allow(RateLimitSlot(pk, _window_sk(start)), remaining=policy.limit - count)
        self._undo(store, pk, start)
        return RateLimitDecision.deny(start + size - now)


class SlidingWindowStrategy(_CounterStrategy):
    """Up to `limit` requests in any rolling window.

    Estimates the rolling count as `previous × (share of the previous window still in range) +
    current`. That needs only two fixed-window counters and is within a few percent of an exact log.
    """

    algorithm = RateLimitAlgorithm.SLIDING_WINDOW

    def acquire(self, store: RateLimitStore, pk: str, policy: RateLimitPolicy, now: int) -> RateLimitDecision:
        size, limit = policy.window_seconds, policy.limit
        start = now - now % size
        elapsed = now - start
        # The next window reads this one as its "previous", so keep it for two windows.
        current = self._count(store, pk, start, ttl=start + 2 * size + COUNTER_TTL_MARGIN_SECONDS)
        previous = store.count(pk, _window_sk(start - size))

        estimate = previous * (size - elapsed) / size + current
        if estimate <= limit:
            return RateLimitDecision.allow(RateLimitSlot(pk, _window_sk(start)), remaining=math.floor(limit - estimate))
        self._undo(store, pk, start)
        return RateLimitDecision.deny(seconds_until_allowed(previous, current - 1, limit, size, elapsed))


def seconds_until_allowed(previous: int, current: int, limit: int, size: int, elapsed: int) -> int:
    """How long until one more request fits, given the counts without it."""
    needed = limit - current - 1  # room the previous window's weighted share must shrink into
    if needed >= 0:
        if previous == 0:
            return 1
        # previous × (size - e) / size <= needed  →  e >= size × (1 - needed / previous)
        return max(1, math.ceil(size * (1 - needed / previous)) - elapsed)
    # This window alone is full: wait for the next one, where today's count becomes "previous".
    until_next = size - elapsed
    if current == 0:
        return until_next
    return until_next + max(0, math.ceil(size * (1 - (limit - 1) / current)))


#: Every available algorithm. `strategy_for` picks from this list; add new ones here.
RATE_LIMIT_STRATEGIES: tuple[RateLimitStrategy, ...] = (
    CooldownStrategy(),
    FixedWindowStrategy(),
    SlidingWindowStrategy(),
)
