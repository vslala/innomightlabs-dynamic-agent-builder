# Token Usage Contribution Guide

`token_usage/` keeps pre-aggregated LLM token counters per agent (and per public API secret key) and reads them back as time series. It has no router: writes come from the chat loop (`src/agents/agentic_loop.py`, also `src/dream/service.py`), reads are exposed through `GET /analytics/agents/{agent_id}/token-usage` in `src/analytics/router.py` and the public API key router (`src/public_api/keys_router.py`).

## Layout

```text
src/token_usage/
  service.py      TokenUsageService: record_usage, get_usage (range normalisation, series building)
  repository.py   TokenUsageRepository: atomic bucket increments, bounded range query
  models.py       TokenUsagePeriod, format_period_key, TokenUsageRecord, response models
```

## Conventions

- **Keys.** `pk=Agent#{agent_id}` (or `SecretKey#{api_key_id}` via `usage_partition`), `sk=TokenUsage#{period}#{period_key}#{llm_model}`. `period` is `day|month|year`; `period_key` is `YYYY-MM-DD`, `YYYY-MM` or `YYYY`. Period key comes before the model so one `sk BETWEEN` query returns every model for a date range; the upper bound uses a `chr(0x10FFFF)` sentinel to cover the model suffix. No GSIs.
- **Writes.** `increment_usage` does three independent `update_item` calls (day, month, year) with `if_not_exists(...) + :n`, doubled under the key's partition when `api_key_id` is given. These are telemetry counters, not a ledger, so there is deliberately no transaction. It returns the day bucket so callers can push a live update.
- **Access.** The data is keyed by agent id only. `record_usage` does no check (it is called from an authorised chat path). `get_usage` takes an already-authorised `Agent`: callers must go through `agent_with(...)` / `require_agent` first, and for a secret key must have confirmed the key belongs to the agent.
- **Errors.** An inverted range raises `HTTPException(400)` in the service. Defaults: day 30 days, month 365 days, year 5 years (`DEFAULT_RANGE_DAYS`).
- **Not the same as analytics.** `TokenUsagePeriod` (day/month/year, pre-aggregated) is intentionally separate from analytics' `TimeseriesBucket` (day/week, scanned on the fly).
- `TokenUsageRecord` is only built by `from_dynamo_item`; never write items from the dataclass.

## How to add a counter or period

- New counter field: add it to the `UpdateExpression` and values in `_increment_bucket`, `TokenUsageRecord`, and the response point model; keep it an `if_not_exists` addition.
- New period: add to `TokenUsagePeriod`, `format_period_key`, `DEFAULT_RANGE_DAYS`, `TokenUsageService._period_start`, and the repository's period loop. Existing buckets for other periods are unaffected.

## Testing

```bash
uv run pytest tests/test_token_usage_*.py -q
uv run ruff check src/token_usage && uv run mypy src/token_usage
```

Tests use the `dynamodb_table` fixture (moto) and call the repository and service directly; they cover accumulation across buckets, per-model items, per-key partitions, range bounds and month/year boundaries.

## Do / Don't

- Do use atomic `update_item` increments; never read-modify-write a counter.
- Do authorise the agent before calling `get_usage`.
- Don't add a transaction here without a billing requirement.
- Don't change `sk` ordering; the range query depends on period key preceding model.
