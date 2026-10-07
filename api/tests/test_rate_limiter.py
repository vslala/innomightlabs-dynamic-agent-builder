"""Rate limit strategies, against the mocked DynamoDB table and a controllable clock."""

import pytest

from src.rate_limits.limiter import RateLimitAlgorithm, RateLimitPolicy, RateLimiter, strategy_for
from src.rate_limits.store import DynamoRateLimitStore
from src.rate_limits.strategies import COOLDOWN_SK, seconds_until_allowed

WINDOW = 3600
#: A window boundary, so tests can place requests at known offsets inside a window.
T0 = 1_800_000_000 - 1_800_000_000 % WINDOW


class Clock:
    def __init__(self, now: int = T0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def limiter(policy: RateLimitPolicy, clock: Clock) -> RateLimiter:
    return RateLimiter(policy, store=DynamoRateLimitStore(), clock=clock)


class BrokenStore:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise RuntimeError("DynamoDB is unreachable")

        return fail


def test_every_algorithm_has_a_strategy():
    for algorithm in RateLimitAlgorithm:
        assert strategy_for(algorithm).algorithm == algorithm


def test_policies_reject_nonsense():
    with pytest.raises(ValueError):
        RateLimitPolicy.fixed_window("X", limit=0, seconds=60)
    with pytest.raises(ValueError):
        RateLimitPolicy.sliding_window("A#B", limit=1, seconds=60)


class TestCooldown:
    policy = RateLimitPolicy.cooldown("TEST_COOLDOWN", seconds=300)

    def test_allows_one_then_waits_out_the_window(self, dynamodb_table):
        clock = Clock()
        cooldown = limiter(self.policy, clock)

        assert cooldown.acquire("1.2.3.4").allowed
        clock.now += 100
        denied = cooldown.acquire("1.2.3.4")
        assert not denied.allowed
        assert denied.retry_after_seconds == 200
        assert cooldown.acquire("5.6.7.8").allowed

    def test_an_expired_lock_that_ttl_has_not_deleted_yet_does_not_block(self, dynamodb_table):
        """The contact form bug: an item TTL hasn't removed yet used to block for hours."""
        clock = Clock()
        cooldown = limiter(self.policy, clock)
        assert cooldown.acquire("1.2.3.4").allowed

        clock.now += 301  # moto, like DynamoDB, still holds the expired item

        assert dynamodb_table.scan()["Items"], "the expired lock item should still exist"
        assert cooldown.acquire("1.2.3.4").allowed

    def test_release_frees_the_lock_but_never_a_newer_one(self, dynamodb_table):
        clock = Clock()
        cooldown = limiter(self.policy, clock)

        first = cooldown.acquire("1.2.3.4")
        cooldown.release(first)
        assert cooldown.acquire("1.2.3.4").allowed  # released, so it's free again

        clock.now += 301
        newer = cooldown.acquire("1.2.3.4")
        cooldown.release(first)  # a stale release for the old lock
        assert newer.allowed
        assert not cooldown.acquire("1.2.3.4").allowed

    def test_two_replicas_share_one_cooldown(self, dynamodb_table):
        """Each server replica has its own limiter; the conditional claim in DynamoDB is what's shared."""
        clock = Clock()
        first, second = limiter(self.policy, clock), limiter(self.policy, clock)
        assert first.acquire("1.2.3.4").allowed
        assert not second.acquire("1.2.3.4").allowed


class TestFixedWindow:
    policy = RateLimitPolicy.fixed_window("TEST_FIXED", limit=3, seconds=WINDOW)

    def test_allows_the_limit_per_window_then_resets(self, dynamodb_table):
        clock = Clock(T0 + 600)
        fixed = limiter(self.policy, clock)

        assert [fixed.acquire("guest").remaining for _ in range(3)] == [2, 1, 0]
        denied = fixed.acquire("guest")
        assert not denied.allowed
        assert denied.retry_after_seconds == WINDOW - 600

        clock.now = T0 + WINDOW
        assert fixed.acquire("guest").allowed

    def test_refused_requests_are_not_counted(self, dynamodb_table):
        clock = Clock()
        fixed = limiter(self.policy, clock)
        for _ in range(3):
            fixed.acquire("guest")
        for _ in range(10):
            assert not fixed.acquire("guest").allowed

        slot = DynamoRateLimitStore().count(fixed._pk("guest"), f"WINDOW#{T0}")
        assert slot == 3

    def test_release_gives_capacity_back(self, dynamodb_table):
        fixed = limiter(self.policy, Clock())
        decisions = [fixed.acquire("guest") for _ in range(3)]
        fixed.release(decisions[0])
        assert fixed.acquire("guest").allowed

    def test_allows_a_double_burst_across_the_window_edge(self, dynamodb_table):
        """The known weakness that SlidingWindow exists to fix."""
        clock = Clock(T0 + WINDOW - 1)
        fixed = limiter(self.policy, clock)
        assert all(fixed.acquire("guest").allowed for _ in range(3))
        clock.now += 1
        assert all(fixed.acquire("guest").allowed for _ in range(3))

    def test_replicas_interleaving_never_exceed_the_limit(self, dynamodb_table):
        clock = Clock()
        replicas = [limiter(self.policy, clock) for _ in range(3)]
        results = [replicas[i % 3].acquire("guest").allowed for i in range(10)]
        assert results.count(True) == 3


class TestSlidingWindow:
    policy = RateLimitPolicy.sliding_window("TEST_SLIDING", limit=4, seconds=WINDOW)

    def test_blocks_the_burst_a_fixed_window_allows(self, dynamodb_table):
        clock = Clock(T0 + WINDOW - 1)
        sliding = limiter(self.policy, clock)
        assert all(sliding.acquire("guest").allowed for _ in range(4))

        clock.now += 1  # a new window, but the previous one still counts in full
        assert not sliding.acquire("guest").allowed

    def test_capacity_returns_as_the_previous_window_slides_out(self, dynamodb_table):
        clock = Clock(T0)
        sliding = limiter(self.policy, clock)
        assert all(sliding.acquire("guest").allowed for _ in range(4))

        clock.now = T0 + WINDOW + WINDOW // 4  # 3/4 of the previous window still in range: 3 used
        assert sliding.acquire("guest").allowed
        assert not sliding.acquire("guest").allowed

    def test_retry_after_is_exactly_when_the_next_request_fits(self, dynamodb_table):
        clock = Clock(T0 + 10)
        sliding = limiter(self.policy, clock)
        assert all(sliding.acquire("guest").allowed for _ in range(4))

        clock.now = T0 + WINDOW + 5
        denied = sliding.acquire("guest")
        assert not denied.allowed

        clock.now += denied.retry_after_seconds - 1
        assert not sliding.acquire("guest").allowed
        clock.now += 1
        assert sliding.acquire("guest").allowed

    def test_starting_fresh_allows_the_full_limit(self, dynamodb_table):
        sliding = limiter(self.policy, Clock(T0 + 123))
        assert [sliding.acquire("guest").remaining for _ in range(4)] == [3, 2, 1, 0]


@pytest.mark.parametrize(
    ("previous", "current", "limit", "elapsed", "expected"),
    [
        (0, 3, 4, 100, 1),                      # one more still fits: minimum wait
        (0, 4, 4, 100, WINDOW - 100 + WINDOW // 4),  # this window is full: into the next, until it slides
        (4, 0, 4, 0, WINDOW // 4),              # previous must shrink by one request's share
        (4, 4, 4, 0, WINDOW + WINDOW // 4),     # both full: wait into the next window
        (0, 0, 4, 0, 1),                        # never really blocked: minimum wait
    ],
)
def test_seconds_until_allowed(previous, current, limit, elapsed, expected):
    assert seconds_until_allowed(previous, current, limit, WINDOW, elapsed) == expected


@pytest.mark.parametrize("fail_open", [True, False])
def test_an_unreachable_store_follows_the_policy(fail_open):
    policy = RateLimitPolicy.fixed_window("TEST_FAIL", limit=1, seconds=60, fail_open=fail_open)
    decision = RateLimiter(policy, store=BrokenStore(), clock=Clock()).acquire("guest")
    assert decision.allowed is fail_open


def test_subjects_are_stored_hashed(dynamodb_table):
    limiter(RateLimitPolicy.cooldown("TEST_HASH", seconds=60), Clock()).acquire("person@example.com")
    item = dynamodb_table.scan()["Items"][0]
    assert "person@example.com" not in str(item)
    assert item["sk"] == COOLDOWN_SK
