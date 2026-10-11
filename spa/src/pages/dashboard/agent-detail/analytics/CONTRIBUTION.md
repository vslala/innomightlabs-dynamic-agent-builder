# Agent Analytics Dashboard Guide

`AgentAnalyticsDashboard.tsx` implements the agent's draggable/resizable analytics workspace using `react-grid-layout`. It gets the agent from detail outlet context; `AgentAnalyticsPage.tsx` is only the route wrapper.

## Layout and flow

- `registry.tsx`: widget metadata, defaults, sizing, singleton/removable/configurable flags.
- `types.ts`: widget-type union, configurations, response contracts, filter state, layouts.
- `constants.ts`: breakpoints, columns, row height, spacing, storage prefix/version.
- `storage.ts`: create/load/save dashboard state and add/remove instances. LocalStorage keys include agent ID and dashboard version; this stores layout/config, not API metrics.
- `events.ts`: current filters and filter-change subscriptions/broadcasts, plus layout-reset events.
- `utils.ts`: date windows, IDs, series transforms, formatting, and layout helpers.
- `api.ts`: local `analyticsApiService` wrapping shared `httpClient` for overview/timeseries queries. This is an existing exception to the usual `src/services/` location; do not bypass the shared client.
- `widgets/`: renderers and their shared frame; see its guide.

Dashboard state loads for the selected agent, filter config becomes a query window, filter events update mounted widgets, and each widget fetches its data. Layout/config changes are saved independently of backend analytics. Keep filter subscription cleanup and per-agent storage isolation intact.

## Adding a widget

1. Extend `WidgetType` and typed config in `types.ts`.
2. Add defaults/constraints to `registry.tsx` and implement a renderer in `widgets/`.
3. Wire rendering and any configuration controls in `AgentAnalyticsDashboard.tsx`; registry metadata alone does not render a new type.
4. Review default layouts and persisted-state compatibility in `storage.ts`; use the version deliberately if the stored shape becomes incompatible.
5. Test transforms and state restoration, then inspect all breakpoints and add/remove/reset behavior.

## Styling and verification

There is no analytics-local CSS Module. The dashboard imports the grid/resizable packages' plain global CSS; renderers use shared UI, utilities, and inline layout. Preserve the widget drag handle and resize behavior; use theme variables for new visuals.

No colocated analytics tests currently exist. Add focused Vitest tests for storage/filter/series behavior. From `spa/`, run `yarn eslint src/pages/dashboard/agent-detail/analytics`, then `yarn test`, `yarn lint`, and `yarn build`. With `yarn dev`, check filter changes, errors/empty data, layout persistence across reload, separate agents, and narrow grid widths.
