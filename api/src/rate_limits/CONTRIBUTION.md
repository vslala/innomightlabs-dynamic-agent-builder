# Rate Limits Contribution Guide

`rate_limits/` holds two unrelated things. (1) Subscription usage limits: how many agents, messages per month and knowledge-base pages a person's plan allows, enforced by a middleware. (2) Request limiters: a small policy/strategy engine for throttling routes (contact form, guest chat, blueprint apply) with DynamoDB counters.

## Layout

```text
src/rate_limits/
  service.py      RateLimitService: plan tier -> limits -> usage -> HTTP 429
  middleware.py   RateLimitMiddleware: matches routes, calls the service
  repository.py   UsageRepository: monthly usage counters (atomic update_item)
  models.py       UsageRecord (dataclass) for the usage item
  policy.py       RateLimitPolicy, RateLimitAlgorithm, RateLimitDecision, RateLimitSlot
  limiter.py      RateLimiter (acquire / release), strategy_for
  strategies.py   Cooldown, FixedWindow, SlidingWindow + RATE_LIMIT_STRATEGIES
  store.py        RateLimitStore protocol and DynamoRateLimitStore
```

## A. Subscription usage limits

- **Keys.** `pk=User#{email}`, `sk=Usage#{YYYY-MM}` for `messages_used` and `kb_pages_used`; `sk=Usage#active` holds `agents_active`. Usage is keyed by email, not account; limits stay per person until billing moves to accounts (KAN-86).
- **Limits** come from `get_pricing_config()` in `src/payments/pricing_config.py` (per-env JSON). Tier = the active subscription's `plan_name`, else `free`. A limit of `0` means unlimited. Superusers (`settings.is_superuser_email`) bypass every check.
- **Enforcement.** The middleware runs after auth (`main.py` registers it first, so it runs after `AuthMiddleware`). It checks `POST /agents`, `.../send-message` (agents and `/builder`) and crawl-job start/run, and returns `JSONResponse` with the 429 `detail` (`message`, `limit`, `current`, `tier`, `upgrade_url`).
- **Counting.** Nothing in this module increments messages or pages on the request path. `lambdas/usage_stream_handler/handler.py` reads DynamoDB stream events and calls `UsageRepository.increment_messages` / `increment_kb_pages`. The service's `record_*` helpers exist but have no callers in `src/`.
- Always update counters with `update_item` and `if_not_exists`, as `repository.py` does.

## B. Request limiters

```mermaid
flowchart LR
    P[RateLimitPolicy] --> L[RateLimiter]
    L -->|strategy_for| S[Cooldown / Fixed / Sliding]
    S --> St[(RateLimitStore: DynamoDB)]
    L --> D[RateLimitDecision]
```

- A caller declares a module-level policy with a constructor (`RateLimitPolicy.cooldown`, `.fixed_window`, `.sliding_window`) and calls `RateLimiter(policy).acquire(subject)`. Examples: `src/contact/router.py` (cooldown), `src/widget/guests.py`, `src/blueprints/service.py`.
- If the guarded work fails, call `limiter.release(decision)` so it does not count.
- Keys: `pk=RATE_LIMIT#{scope}#{sha256(subject)[:16]}`, `sk=COOLDOWN` or `WINDOW#{start}`. Only a hash of the subject (IP, email) is stored. `scope` must be stable and contain no `#`.
- `ttl` only cleans up; every decision compares stored timestamps with the clock because TTL can lag 48h.
- `fail_open` (default True) decides what happens when DynamoDB errors; set `False` for limits that guard cost or abuse.
- Refused requests undo their increment so a blocked client is not penalised further.

## How to add a limit

- Throttle a route: add a `RateLimitPolicy` constant next to the route, `acquire` at the top, raise 429 with `Retry-After: decision.retry_after_seconds` when not allowed.
- New plan quota: add the field to the pricing JSONs and `PricingTierLimits`, a `check_*` method in `service.py`, a route match in `middleware.py`, and a counter path in the usage stream handler.
- New algorithm: add a value to `RateLimitAlgorithm`, a class with `acquire`/`release` in `strategies.py`, and append it to `RATE_LIMIT_STRATEGIES`. `strategy_for` is the only selector.

## Testing

```bash
uv run pytest tests/test_rate_limits.py tests/test_rate_limiter.py -q
uv run ruff check src/rate_limits && uv run mypy src/rate_limits
```

Limiter tests inject a fake `Clock` and a `BrokenStore` into `RateLimiter` and use `DynamoRateLimitStore` on moto. Usage-limit tests use `test_client`, `auth_headers` and `dynamodb_table`, seeding `Usage#` items and subscriptions directly.

## Do / Don't

- Do pick behaviour by choosing a policy constructor; never branch on algorithm in callers.
- Do keep new algorithms built from the `RateLimitStore` atomic operations.
- Don't read-then-write counters; use `add` / conditional `claim`.
- Don't store raw IPs or emails in rate limit keys.
- Don't duplicate plan limits in code; they live in the pricing JSON.
