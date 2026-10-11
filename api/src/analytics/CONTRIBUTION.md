# Analytics Contribution Guide

`analytics/` serves per-agent dashboard numbers: an overview (totals, ratios, distributions, top conversations and users) and conversation, message and unique-user time series, across dashboard chats and embedded-widget chats. It computes everything on demand by scanning existing conversations and messages; it stores nothing. Token usage is mounted on the same router but lives in `src/token_usage/`.

## Layout

```text
src/analytics/
  router.py     /analytics/agents/{id}/overview | timeseries | token-usage; `sources` query parsing
  service.py    AnalyticsService: collect conversations and messages, build totals/ratios/series
  models.py     Query enums (AnalyticsSource, TimeseriesMetric, TimeseriesBucket) and response models
```

## Conventions

- **No storage of its own.** The service reads `ConversationRepository.find_all_by_user(partition)` for dashboard chats, `WidgetConversationRepository.find_by_agent` (paged) for widget chats, and `MessageRepository.find_by_conversation` for messages. Repositories are injected through the constructor for tests.
- **Access.** Routes use `can_read_agent = agent_with("agents:Get")` (`src/agents/access.py`): the path agent is loaded and the IAM action checked before the handler runs. Dashboard conversations are read from `agent.owner_partition`, the agent owner's partition, so every member sees the same numbers.
- **Bounded scans.** `MAX_CONVERSATIONS_SCANNED` (500), `MAX_MESSAGES_SCANNED` (10,000) and `MAX_WINDOW_DAYS` (90) cap the work. When a cap hits, `_truncate` sets `meta.truncated` and `truncation_reason`; responses always include `meta`. Keep that honest when adding a metric.
- **Time.** Windows default to the last 30 days, are normalised to UTC (`normalize_window`), validated (`validate_window`, 400 on bad ranges), and bucketed in the caller's `tz` (`parse_timezone`, 400 on unknown zones). Empty buckets are included (`iter_bucket_starts`).
- **Sources.** `sources` is a comma separated list parsed by `parse_sources` (400 on unknown values); unset means both. Widget users are identified by `visitor_id`; guests are labelled `(guest, unverified)`.
- **Errors.** `HTTPException` with 400 for bad input. No custom exception types.

## How to add a metric

1. Add a value to `TimeseriesMetric` in `models.py` (and a field to `AnalyticsTotals` if it is also an overview number).
2. Compute it in `AnalyticsService._build_timeseries` / `_build_totals` from the already collected `ConversationRecord`s; do not add another repository read.
3. Update the SPA chart consumer (`spa/`) if it lists metrics.
4. Test the helper or builder in `tests/test_analytics_service.py` (pure functions like `percentile`, bucket helpers, identity) and the route in `tests/test_analytics_router.py`.

## Testing

```bash
uv run pytest tests/test_analytics_*.py tests/test_token_usage_*.py -q
uv run ruff check src/analytics && uv run mypy src/analytics
```

Service tests use fake repositories or `dynamodb_table` (moto); router tests use `test_client` and `auth_headers`.

## Do / Don't

- Do reuse the collected records for every metric in one request.
- Do report truncation instead of silently returning partial numbers.
- Don't add pre-aggregation or new item types here; if a number needs durable counters, follow `src/token_usage/`.
- Don't skip `agent_with`; the service takes a `partition` and `agent_id` and trusts the caller.
