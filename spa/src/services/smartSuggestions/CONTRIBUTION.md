# Smart Suggestions Service Guide

`SmartSuggestionService.ts` handles configuration and one-shot suggestions, not chat SSE.

- Settings GET/PUT use `/smart-suggestions/settings`; schema GET uses `/settings/schema` beneath that prefix. `is_configured` and timestamps are response fields, not settings request fields.
- Suggest POSTs to `/smart-suggestions` with `suggestion_type`, `query`, optional `current_value` and typed unknown-valued context.
- A result's `value` is distinct from optional `display_text` and metadata. Preserve both so the UI doesn't submit a human-readable label as the actual suggestion value.
- Provider/model configuration and validation stay backend-owned via FormSchema; debounce/cancellation and form state belong to consumers.

No adjacent tests currently. Add settings request-field and value/display response regressions; from `spa/`, run `yarn test src/services/smartSuggestions` once added. Full checks: [services guide](../CONTRIBUTION.md).
