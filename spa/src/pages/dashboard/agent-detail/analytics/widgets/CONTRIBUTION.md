# Analytics Widgets Guide

Widgets are agent-scoped renderers inside the parent grid, not routes. Read `../CONTRIBUTION.md` for registration, storage, and filters.

## Layout

- `AnalyticsWidgetFrame.tsx`: shared title, drag handle (`analytics-widget-drag-handle`), refresh/configure/remove controls, and truncation indicator.
- `DashboardFiltersWidget.tsx`: date preset/source selection and filter broadcasts; registry makes it singleton and non-removable.
- `OverviewStatsWidget.tsx`: conversation/message/user/active-day totals from overview data.
- `MessageMixWidget.tsx`: message distribution from overview data.
- `TimeseriesWidget.tsx`: Recharts line/bar series for configured metrics; shared source grouping/merging lives in parent `utils.ts`.
- `TopActivityWidget.tsx`: ranked conversation/user activity from overview data.
- `shared.tsx`: loading/error/empty states and filter footnotes.

Data widgets initialize from current filters, subscribe to changes, query `analyticsApiService` with agent/date/timezone/source arguments, and support explicit refresh. Preserve effect cleanup and guards against stale responses. Use the shared states so failed requests do not appear as zero-valued successful results.

## Extension and styles

Use `AnalyticsWidgetBaseProps` and a specific config type. Compose the frame, retain drag affordances, and register/render the widget in the parent as described there. Keep chart transforms in `utils.ts` when reusable; do not create another analytics transport.

This directory has no CSS files. Existing styles are shared UI classes, utilities, and inline layout; grid/resizer global CSS is imported by the parent. For substantial new styling, add an owning local stylesheet rather than generic global chart/card overrides. Check chart containers at resized heights and widths.

## Verification

No colocated widget tests exist. Add behavior tests for new transforms/filter handling. From `spa/`: `yarn eslint src/pages/dashboard/agent-detail/analytics/widgets`, `yarn test`, `yarn lint`, `yarn build`. Use `yarn dev` to exercise refresh, filters, empty/error/truncated states, configuration, removal, and resizing.
