# Low Level Design: Automation Workflow Editor Redesign

Date: 2026-09-13
Status: Implemented (2026-09-13)
Owner: InnomightLabs SPA/API

> ## As built
>
> All seven phases are implemented. Verification: `uv run pytest` 633 passed /
> 1 skipped; `yarn test` 56 passed; `yarn build` and `tsc -b` clean; `yarn lint`
> reports nothing in the new files.
>
> Deviations from the plan below, and why:
>
> | Planned | As built | Reason |
> |---|---|---|
> | `StopCard.tsx`, `BranchLane.tsx` as files | Both live inside `ConditionCard.tsx` | Neither is used anywhere else, and a stop is a rendering of a lane edge, not a component with its own state |
> | `useActionCatalog.ts` | Folded into `useAutomationDraft` | The catalog loads with the graph and is refreshed by the same code path after a skill install |
> | Client-side smart-value catalog only | Added `chain/conditionExpression.ts` and `chain/aliases.ts` | The condition grammar and the alias rules are backend contracts that the editor must mirror exactly; both are pure and tested |
> | Token parsing in `chain/smartValues.ts` | Moved to `components/forms/smartValueTokens.ts` | The field component owns insertion, and `components/` may not import from `pages/`; one owner instead of two copies |
> | Negative margins to go full-bleed | `DashboardLayout` treats the workspace route as full-bleed | The mechanism already existed for the conversation view |
> | Runs drawer fixed to the viewport | Drawer is a flex child; the chain scrolls between top bar and drawer | A viewport-fixed drawer would have covered the dashboard sidebar |
> | Analytics tab shows the old placeholder | Summary computed from the loaded runs | Says something true without inventing an endpoint |
>
> Also added, not in the plan: `vitest` as a dev dependency plus a `yarn test`
> script (the SPA had no test runner, and phase 2 called for unit tests), and
> `ConfirmationDialog` exported from the UI barrel (it existed but was unexported).

## Summary

Replace the four-route, canvas-plus-multiplexed-panel automation builder with a single-page **linear rule chain** workspace modelled on Atlassian Automation: a vertical `WHEN → THEN → IF` column of inline-expanding step cards, with branch lanes indented under condition steps.

Everything a user needs to build, configure, test, and inspect a workflow lives on one screen:

- The trigger is the first card, configured inline (no separate Triggers page).
- Each step expands in place to show its schema-driven parameter form **and** its last-run input/output side by side.
- Smart values are readable aliases (`{{ steps.gmail_search.output.response_text }}`) inserted through a `{{` typeahead, not hand-pasted UUID paths.
- Edits autosave; there is no Save button.
- Runs are a bottom drawer whose selected run hydrates the same step cards (no separate Runs page).

The React Flow canvas is retired as the primary editing surface. The backend graph model is unchanged in shape — edges are still the source of truth — but the UI no longer asks the user to draw them.

### Decisions taken

| Decision | Choice | Consequence |
|---|---|---|
| Layout paradigm | Atlassian-style linear rule chain | `@xyflow/react` drops out of the builder; graph↔chain linearization becomes the core frontend algorithm |
| Backend scope | Implement node aliases + smart values | Executes the pending [LLD-automation-smart-values](./LLD-automation-smart-values.md); adds `alias`, `context.steps`, `smart_values.py`, preview endpoint |
| Persistence | Debounced autosave | Needs a save queue plus a **draft validation mode** on the backend (see §7.2) |
| Route structure | Collapse all four routes into one workspace | Side nav removed; `triggers`/`runs`/`analytics` become redirects into panel state |

## Goals

- One screen, zero navigation, to author a complete workflow.
- Step parameters and the data flowing through that step are visible simultaneously.
- Referencing a previous step's output takes one keystroke (`{{`) and produces a stable, readable token.
- Structurally impossible to create an invalid graph shape through the UI.
- Adding a step is a search-and-pick action over the existing action catalog, not a dropdown buried in an inspector.
- Every backend affordance already built (action forms, install forms, connector status, cron smart-suggestion, key-value inputs) is surfaced.

## Non-Goals

- Free-form DAG authoring (fan-out to parallel steps, manual edge drawing). The chain supports a spine plus `true`/`false` lanes. Graphs that exceed this render read-only (§6.5).
- Loops. Backend rejects cycles (`validation.py:347`).
- Run streaming. Polling at 1.5s is retained; SSE was explicitly deferred.
- Partial / resume-from-step runs. The runner executes whole graphs (`runner.py:206`).
- Webhook trigger authoring. The enum and GSI keys exist (`models.py:37`, `models.py:521`) but there is no form builder, no ingress route, and no lifecycle — out of scope, and the WHEN card must not offer it.
- Multi-user collaborative editing.

## 1. Current State

### 1.1 What the backend provides

`api/src/automations/` is graph-native and in good shape:

- `Automation` + `AutomationNode` (`start` | `action` | `condition` | `final`) + `AutomationEdge` (label `next` | `true` | `false`) + `AutomationTrigger` (`manual` | `schedule` | `webhook`), single-table DynamoDB under `Automation#{automation_id}` (`models.py:381-542`).
- `GET /{id}/graph`, `PUT /{id}/graph` (whole-graph replace), plus **per-node / per-edge / per-trigger CRUD that the SPA never calls** (`router.py:262-413`).
- `GET /{id}/action-catalog` returns, per skill action: `input_schema`, `action_form` (a full `Form` schema), `install_schema`, `connectors`, `available`, `disabled_reason` (`service.py:622-723`). This is the richest and least-used endpoint in the module.
- `GET /{id}/triggers/forms/{trigger_type}` returns declarative forms for `manual` and `schedule` only (`triggers/schemas.py`), including an AI `SmartSuggestionConfig` for cron and a `key_value` input for scheduled run input.
- Runs are async: `POST /{id}/test-run` returns 202, then `GET /{id}/runs/{run_id}` yields `node_results` with `input`, `output`, `error`, and lifecycle/tool-call `events`.

### 1.2 What breaks in the current UI

| # | Problem | Evidence |
|---|---|---|
| 1 | Work is split across four routes behind a 15rem side nav. The **trigger** — the start of every workflow — is edited on a different page from the steps it starts. | `App.tsx:137-141`, `components/AutomationSideNav.tsx:6-11`, `AutomationTriggersPage.tsx` |
| 2 | One 24rem `aside` is multiplexed across four modes by `panelMode`. Opening Smart Values **unmounts the step form you were editing**; so does starting a test run. Parameters and the values you want to put in them can never be on screen together. | `AutomationBuilderPage.tsx:69`, `:1343-1430` |
| 3 | Smart values are a copy-paste ritual over raw UUID paths: `{{ $.nodes.action-bf61da39-….output.response_text }}`. No alias layer exists — there is no `alias` field in `models.py` and no `api/src/automations/smart_values.py`, so [LLD-automation-smart-values](./LLD-automation-smart-values.md) is written but unimplemented. | `AutomationBuilderPage.tsx:183-315`, `runner.py:621-665` |
| 4 | A step's real input/output only exists on the Runs page, disconnected from the form where it would be used. | `AutomationRunsPage.tsx:170-191` |
| 5 | `normalizeGraph` rewrites node positions on load and sets `dirty` before the user touches anything; nodes drift off-viewport badly enough to need a "Place on canvas" button; `fitView` re-fires on every node-count change. | `AutomationBuilderPage.tsx:406-519`, `:1775`, `:987-993` |
| 6 | **Deleting a middle step corrupts the graph.** `deleteNode` drops all incident edges without reconnecting, so the predecessor loses its outgoing edge and the tail becomes unreachable — the next save fails `_require_outgoing` / reachability. | `AutomationBuilderPage.tsx:804-812` vs `validation.py:368-375`, `:323-332` |
| 7 | The only way to add a step appends before `Done` via a floating rail button; there is no insert-between affordance. Choosing what the step does is a long flat `Select` of `"{skill}: {action}"` strings with no search, grouping, or descriptions. | `AutomationBuilderPage.tsx:1091-1103`, `:1802-1843` |
| 8 | Test input is raw hand-written JSON; the run result renders as a step list in the 24rem column instead of as status on the steps themselves. | `AutomationBuilderPage.tsx:908`, `:1580-1624` |

### 1.3 Reusable assets

The redesign leans on machinery that already exists:

- `SchemaForm` already supports `onChange` (per-keystroke) and `hideActions` — exactly what autosave needs, no fork required (`components/forms/SchemaForm.tsx:25`, `:30`).
- `FormField` is a clean dispatcher over `./fields/*` with an established "extra control under a text field" seam used by `SmartSuggestionControl` (`components/forms/FormField.tsx:62-74`). The smart-value typeahead attaches at the same seam.
- `attr: { smart_values: "true" }` is already emitted by the marketplace publish flow (`AutomationDetailLayout.tsx:495-497`) but **no field renderer implements it** — the contract exists and is unclaimed.
- `collectInputPlaceholders` already scans a graph for `{{ inputs.<key> }}` tokens (`AutomationDetailLayout.tsx:544-559`); the same scanner, retargeted at `input.*`, generates the test-run form.
- `StepInspector`, `JsonTreeViewer`, `AccordionPanel`, `StatusBadge`, and the run-display helpers in `runDisplay.ts` (`getRuntimeLogSteps`, `getToolCalls`, `getLifecycleEvents`) move into the step card unchanged.

## 2. Target UX Model

One route, four zones.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ‹  ⚡ Weekly Inbox Digest      ● Saved    [Draft ▾]  [▷ Test]  [ ⋯ ]     │  A. Top bar
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌────────────────────────────────────────────────────────────┐         │
│   │ WHEN   ⏰  Every weekday at 9:00 AM · UTC              ▾  │         │  B. Chain
│   └────────────────────────────────────────────────────────────┘         │
│                            │                                            │
│   ┌────────────────────────────────────────────────────────────┐         │
│   │ THEN   📧  Gmail: search                    ✓ 12 items  ▴  │         │
│   ├────────────────────────────────────────────────────────────┤         │
│   │   Reference name   gmail_search                            │         │
│   │   Query            [ is:unread newer_than:7d          ]    │         │
│   │   Max results      [ 50 ]                                  │         │
│   │   ────────────────────────────────────────────────────     │         │
│   │   Last run  ✓ 2m ago            [ Input ] [ Output ] [⋯]   │         │
│   │   ┌──────────────────────────────────────────────────┐     │         │
│   │   │ ▾ messages  (12)                                 │     │         │
│   │   │   ▸ [0]  { subject: "Q3 recap", … }   ⟨ insert ⟩ │     │         │
│   │   └──────────────────────────────────────────────────┘     │         │
│   └────────────────────────────────────────────────────────────┘         │
│                            ⊕                                            │
│   ┌────────────────────────────────────────────────────────────┐         │
│   │ IF     ◇  gmail_search.output.messages is not empty     ▾  │         │
│   └────────────────────────────────────────────────────────────┘         │
│        ├─── true ──┐                                                     │
│        │   ┌────────────────────────────────────────────────┐            │
│        │   │ THEN  🤖  Summarize                    ⚠   ▾  │            │
│        │   └────────────────────────────────────────────────┘            │
│        │            ⊕                                                    │
│        └─── false ── ⊘  Stop · nothing else runs                         │
│                            │                                            │
│   ┌────────────────────────────────────────────────────────────┐         │
│   │ END    ✓  Done                                             │         │
│   └────────────────────────────────────────────────────────────┘         │
│                                                                          │
│                        [ ⊕ Add step ]                                    │
├──────────────────────────────────────────────────────────────────────────┤
│ ▲ RUNS   ✓ 2m ago · ✗ 1h ago · ✓ 3h ago · ✓ 1d ago          [Analytics]  │  C. Runs drawer
└──────────────────────────────────────────────────────────────────────────┘
                                                  D. Add-step palette (⌘K / ⊕)
```

### A. Top bar

Replaces both `automation-detail__header` and `automation-builder__toolbar` (today there are two stacked headers).

- Back chevron, inline-editable title (click to edit, autosaves), inline-editable description on a second line.
- **Save state chip**: `● Saved` / `◌ Saving…` / `⚠ Save failed — retry`. Never a button.
- **Status control**: `Draft ▾` → `Active` / `Disabled`. Activating runs strict backend validation; a 422 opens the issues panel (§5.6) rather than silently failing.
- `▷ Test` opens the test panel (§5.5).
- `⋯` overflow: Publish to marketplace (existing dialog, moved), Duplicate, Delete.

### B. Chain column

Centred, `max-width: 46rem`, vertically scrolling. Card kinds:

| Card | Backend entity | Notes |
|---|---|---|
| `WHEN` | `AutomationTrigger[]` + the `start` node | One card per trigger; `+ Add trigger` for a second (backend supports N triggers per start) |
| `THEN` | `AutomationNode(type=action)` | Expands to action picker + `action_form` + last-run data |
| `IF` | `AutomationNode(type=condition)` | Expands to the condition builder; renders `true`/`false` lanes beneath |
| `⊘ Stop` | An edge from the condition straight to the `final` node | Not a node type — a rendering of "this lane goes directly to Done" |
| `END` | `AutomationNode(type=final)` | Read-only, always last |

Between every pair of cards sits a hover-revealed `⊕` insert affordance. At the tail of each branch lane too.

### C. Runs drawer

Bottom-docked, three heights: **rail** (default — status chips for the last 5 runs), **half**, **full**. Selecting a run puts the whole workspace in *run view*: each step card shows that run's status, duration, input, and output inline. Deselecting returns to the last run. Tabs: `Runs` | `Analytics` (the current placeholder page moves here).

### D. Add-step palette

A command palette (`⌘K`, or clicking any `⊕`) over the action catalog: fuzzy search, grouped by skill, description as secondary line, connector/availability state as a trailing chip. Sections: `Actions` (from `action-catalog`), `Logic` (`IF/ELSE`, `Stop`), `Needs setup` (catalog items with `install_schema`, which open their install form inline in the new card instead of being unselectable).

## 3. Step Card Anatomy

The step card is the centrepiece: it must make "update the step details without moving between screens" literally true.

### 3.1 Collapsed

```
│ THEN   📧  Gmail: search                        ✓ 12 items  ▴  │
  ────    ──  ──────────────                      ────────────
  kind   icon  action label                       last-run chip
```

The summary line is generated per action from its config — `Gmail: search` plus a one-line rendering of the primary argument. Badges: `⚠` for a client-detected config problem, `◌` while saving.

### 3.2 Expanded

Three stacked sections inside one card (not tabs — everything visible at once):

1. **Identity**: step name, `Reference name` (the alias — see §8.1) with helper text `Used in smart values, e.g. {{ steps.gmail_search.output.response_text }}`, description.
2. **Parameters**: `SchemaForm` over `catalogItem.action_form`, `hideActions`, wired to `onChange` → autosave. When no `action_form` exists, fall back to `AutomationJsonEditor` over `config.arguments` (today's behaviour, retained as escape hatch).
3. **Data**: the last run's `input` / `output` / `events` for this node, rendered with the existing `JsonTreeViewer` + `runDisplay.ts` helpers. Every leaf in the output tree has an `⟨ insert ⟩` affordance that writes the smart-value token for that path into the last-focused parameter field — the single most valuable interaction in the redesign, and the thing the current split across Builder/Runs pages makes impossible.

Only one card is expanded at a time by default (accordion), with a pin to keep several open.

## 4. Frontend Architecture

### 4.1 Module layout

```txt
spa/src/pages/dashboard/automations/
  AutomationWorkspacePage.tsx          NEW  replaces AutomationBuilderPage
  AutomationDetailLayout.tsx           EDIT strip header + side nav, keep publish dialog
  AutomationRunsPage.tsx               DEL  → redirect (logic moves into runs drawer)
  AutomationTriggersPage.tsx           DEL  → redirect (logic moves into WHEN card)
  AutomationAnalyticsPage.tsx          MOVE → drawer tab
  AutomationBuilderPage.tsx            DEL
  chain/
    chainModel.ts        ChainItem types + linearize(graph)
    chainOperations.ts   pure graph mutations (insert/delete/move/convert)
    chainValidation.ts   client-side draft validation → per-card issues
    smartValues.ts       alias catalog, token parse/insert, run-sample enrichment
    actionSummary.ts     collapsed-card one-line config summaries
  components/
    WorkspaceTopBar.tsx
    ChainColumn.tsx          renders ChainItem[] recursively
    TriggerCard.tsx          WHEN
    StepCard.tsx             THEN (identity + params + data)
    ConditionCard.tsx        IF + lanes
    BranchLane.tsx
    StopCard.tsx
    EndCard.tsx
    InsertAffordance.tsx     the ⊕
    AddStepPalette.tsx       ⌘K catalog search
    ConditionBuilder.tsx     structured left/op/right editor
    StepDataPanel.tsx        last-run input/output + insert-token leaves
    RunsDrawer.tsx
    TestPanel.tsx
    IssuesPanel.tsx
    AutomationJsonEditor.tsx KEEP
  hooks/
    useAutomationDraft.ts    graph state + autosave queue
    useAutomationRuns.ts     run list, polling, selected-run hydration
    useActionCatalog.ts
  styles.css                 EDIT  canvas rules out, chain rules in
```

New shared field control:

```txt
spa/src/components/forms/fields/SmartValueTextField.tsx   NEW
spa/src/components/forms/SmartValueControl.tsx            NEW  ({{ typeahead + token chips)
spa/src/components/forms/FormField.tsx                    EDIT dispatch on attr.smart_values
```

### 4.2 The chain model

```ts
// chain/chainModel.ts
export type ChainItem =
  | { kind: "trigger"; triggers: AutomationTrigger[]; startNode: AutomationNode }
  | { kind: "step"; node: AutomationNode }
  | { kind: "condition"; node: AutomationNode; lanes: ChainLane[] }
  | { kind: "end"; node: AutomationNode };

export interface ChainLane {
  label: "true" | "false";
  items: ChainItem[];
  /** lane runs straight to the final node → render as ⊘ Stop */
  stops: boolean;
}

export interface Chain {
  items: ChainItem[];
  /** node ids that could not be expressed linearly; non-empty ⇒ read-only mode */
  unsupported: string[];
}
```

`position` is **no longer read**. Order is derived entirely from edges, which is deterministic because the chain is a canonical shape. On save, `position` is written as a derived layout hint (`{ x: laneDepth * 280, y: index * 120 }`) purely so legacy readers and the marketplace import path keep working; nothing depends on it.

### 4.3 Linearization

```ts
export function linearize(graph: AutomationGraphResponse): Chain {
  const nodeById = new Map(graph.nodes.map((n) => [n.node_id, n]));
  const outgoing = groupBy(graph.edges, (e) => e.source_node_id);
  const start = graph.nodes.filter((n) => n.type === "start");
  const final = graph.nodes.find((n) => n.type === "final");
  if (start.length !== 1 || !final) return unsupportedChain(graph);

  const order = topoOrder(start[0].node_id, outgoing);   // index per node id
  const unsupported: string[] = [];

  function walk(fromNodeId: string, stopAt: string | null): ChainItem[] {
    const items: ChainItem[] = [];
    let cursor: string | null = fromNodeId;
    while (cursor && cursor !== stopAt) {
      const node = nodeById.get(cursor);
      if (!node) break;

      if (node.type === "final") {
        items.push({ kind: "end", node });
        break;
      }

      if (node.type === "condition") {
        const t = edgeFor(outgoing, cursor, "true");
        const f = edgeFor(outgoing, cursor, "false");
        if (!t || !f) { unsupported.push(cursor); break; }
        const join = findJoin(t.target_node_id, f.target_node_id, outgoing, order);
        items.push({
          kind: "condition",
          node,
          lanes: [
            lane("true", t.target_node_id, join),
            lane("false", f.target_node_id, join),
          ],
        });
        cursor = join;
        continue;
      }

      items.push({ kind: "step", node });                  // action
      const next = edgeFor(outgoing, cursor, "next");
      if (!next || (outgoing.get(cursor)?.length ?? 0) > 1) {
        unsupported.push(cursor);                           // fan-out: not linear
        break;
      }
      cursor = next.target_node_id;
    }
    return items;
  }

  function lane(label: "true" | "false", head: string, join: string | null): ChainLane {
    const stops = head === final!.node_id;
    return { label, stops, items: stops ? [] : walk(head, join) };
  }

  return {
    items: [
      { kind: "trigger", triggers: graph.triggers, startNode: start[0] },
      ...walk(edgeFor(outgoing, start[0].node_id, "next")!.target_node_id, null),
    ],
    unsupported,
  };
}
```

**Join detection.** The point where two branch lanes reconverge is the first node, in topological order from start, reachable from both lane heads:

```ts
function findJoin(
  trueHead: string,
  falseHead: string,
  outgoing: Map<string, AutomationEdge[]>,
  order: Map<string, number>,
): string | null {
  const t = descendants(trueHead, outgoing);   // inclusive of the head
  const f = descendants(falseHead, outgoing);
  const shared = [...t].filter((id) => f.has(id));
  if (shared.length === 0) return null;
  return shared.reduce((best, id) => (order.get(id)! < order.get(best)! ? id : best));
}
```

This is well defined because the backend guarantees acyclicity (`validation.py:347-365`) and that the `final` node is reachable from every path, so two lanes always share at least the `final` node.

### 4.4 Chain operations

All pure `(graph, args) => graph`, in `chainOperations.ts`, unit-tested without React. Each operation maintains the invariants the backend validates, so an invalid *shape* becomes unreachable through the UI.

```ts
insertStep(graph, { afterNodeId, laneLabel?, type: "action" | "condition" }): GraphMutation
deleteStep(graph, nodeId): GraphMutation
moveStep(graph, nodeId, direction: "up" | "down"): GraphMutation
convertStepType(graph, nodeId, type): GraphMutation
setStepAction(graph, nodeId, item: AutomationActionCatalogItem): GraphMutation
setLaneStops(graph, conditionNodeId, label, stops: boolean): GraphMutation
```

**insertStep** splices rather than appends. Given `A --label--> B`, inserting `N` retargets the existing edge to `A --label--> N` and adds `N --next--> B`. A `condition` insert additionally creates `N --true--> B` and `N --false--> B` (both lanes initially rejoin, so neither is a dead end).

**deleteStep** reconnects, fixing bug #6: for each incoming edge `P --label--> N`, retarget it to `N`'s `next` target, then drop `N` and its outgoing edges. A condition delete keeps the `true` lane and splices the `false` lane's steps out (with a confirmation naming how many steps are discarded).

**setLaneStops(…, true)** retargets the lane edge at the `final` node and deletes the now-unreachable lane steps — this is how `⊘ Stop` is expressed, since there is no `stop` node type and `final` may not have outgoing edges (`validation.py:66-71`).

`GraphMutation` carries the next graph plus how to persist it:

```ts
interface GraphMutation {
  graph: AutomationGraphResponse;
  persist: "structural" | { node: string; fields: NodePatchFields };
}
```

## 5. Interaction Design Details

### 5.1 Adding a step

`⊕` → palette → pick. For an already-available action: create the node with `config` from the catalog item, name from `item.label`, alias auto-slugged, and expand the new card with focus in the first parameter field. For a `Needs setup` item (`install_schema` present): the card is created in a "setup" state rendering `install_schema` inline; on submit, `POST /{id}/skills?skill_id=…` then refresh the catalog and swap to the parameter form. Today this hijacks the whole side panel via `panelMode === "configure"` (`AutomationBuilderPage.tsx:1385-1406`); now it stays inside the card that needs it.

### 5.2 Condition builder

Replaces the raw expression `Input` (`AutomationBuilderPage.tsx:1908-1928`) with the structured editor the original LLD specified but was never built: left operand (smart-value picker), operator (`is not empty` / `is empty` / `equals` / `not equals`), right value (literal or smart value). Compiles to the expression grammar the runner actually supports — truthy, `==`, `!=` (`runner.py:667-675`):

```ts
compile({ left: "steps.gmail_search.output.messages", op: "truthy" })
  // → "steps.gmail_search.output.messages"
compile({ left: "input.plan", op: "eq", right: "pro" })
  // → "input.plan == 'pro'"
```

Round-trips by parsing the stored expression; unparseable expressions fall back to a raw text field with a note, so hand-written conditions survive.

### 5.3 Smart values

Three surfaces, one catalog (`chain/smartValues.ts`):

1. **`{{` typeahead** in any smart-value-enabled field. Grouped: `Input`, `Trigger`, `Previous steps` (only steps that precede this one in the chain — enforced by chain position, which the current implementation only approximates by filtering the current node id at `AutomationBuilderPage.tsx:206-212`), `Last step`. Each row shows the step name, alias, type, and — when a run is selected — the resolved sample value.
2. **`⟨ insert ⟩` on output-tree leaves** in any step's Data section.
3. **Token chips**: `{{ … }}` runs inside a field render as a chip with a tooltip showing the resolved value from the selected run, and a warning state for unknown aliases/fields.

Catalog sources: static per-node-type fields (as enumerated in the smart-values LLD), plus dynamic paths discovered by walking `run.context.steps[alias]` of the selected run.

### 5.4 Autosave

See §7 for the mechanism. UI contract: field edits show `◌ Saving…` in the top bar within 800ms and settle to `● Saved`; structural edits flush immediately. A failed save shows `⚠ Save failed` with retry and keeps local state — never discards the user's edit.

### 5.5 Test panel

Opens as a right-hand sheet (does not replace the chain). Manual input is a **generated form**, not raw JSON: scan every node config for `{{ input.<key> }}` tokens using the placeholder scanner already written for marketplace publish (`AutomationDetailLayout.tsx:544-559`), and render one labelled field per detected key. A `{ } JSON` toggle exposes the raw editor for anything the scan misses. On run: flush pending saves → `POST /{id}/test-run` → poll `GET /{id}/runs/{run_id}` at 1.5s → stream results into the step cards (each card lights up as its result appears) and into the drawer.

### 5.6 Validation and issues

Two layers:

- **Client, continuous** (`chainValidation.ts`): mirrors the cheap rules — required action arguments missing (from `input_schema.required`), empty agent/prompt, condition with no expression, unset action. Produces `{ nodeId, severity, message }[]` → `⚠` badges on cards and a count in the top bar. Never blocks editing.
- **Backend, authoritative**: on activate (`service.py:205-213`) and on test-run (`router.py:431`). `AutomationValidationError` returns a single string, so it renders as a banner in the issues panel. Mapping errors to specific cards is left to the client layer; adding `node_id` to backend validation errors is a follow-up, not part of this change.

## 6. Routing Changes

```tsx
// App.tsx
<Route path="automations/:automationId" element={<AutomationDetailLayout />}>
  <Route index element={<AutomationWorkspacePage />} />
  <Route path="triggers"  element={<Navigate to=".." replace state={{ focus: "trigger" }} />} />
  <Route path="runs"      element={<RedirectToWorkspace panel="runs" />} />
  <Route path="analytics" element={<RedirectToWorkspace panel="analytics" />} />
</Route>
```

Workspace panel state lives in the query string so everything stays deep-linkable and shareable:

- `?step=<node_id>` — expanded card
- `?panel=runs|analytics` — drawer open, and at which tab
- `?run=<run_id>` — drawer open with that run selected and the chain in run view

`/runs?run=X` redirects to `?panel=runs&run=X`, preserving existing links. `AutomationSideNav.tsx` is deleted. `AutomationDetailLayout` keeps only automation loading, outlet context, and the publish dialog; its header collapses into the workspace top bar so the builder gets the full page height (today two headers plus a side nav consume it, forcing the `calc(100vh - 13rem)` gymnastics in `styles.css`).

## 7. Persistence Design

### 7.1 Two paths, deliberately

| Edit kind | Endpoint | Timing | Why |
|---|---|---|---|
| Field (`name`, `description`, `config`, `alias`) | `PATCH /{id}/nodes/{node_id}` | debounced 800ms, coalesced per node | Idempotent, high frequency, touches one entity |
| Structural (insert, delete, move, convert, lane change) | `PUT /{id}/graph` | immediate flush | Multi-entity and must be atomic |
| Trigger | `POST`/`PATCH`/`DELETE /{id}/triggers[/{trigger_id}]` | on submit | Has scheduler side effects (`service.py:457`, `:489`) |

A structural change is 1 node write plus 1–2 edge rewires. Doing that as three separate calls would leave the stored graph transiently invalid and could fail mid-sequence; `PUT /{id}/graph` writes it in one validated operation (`service.py:322-332`). Two hard constraints on that endpoint:

1. **Always send the complete node and edge set.** `_run_removed_node_lifecycle` (`service.py:305-320`) runs skill-delete lifecycle hooks for any node absent from the payload — a partial payload destroys skill installs.
2. **Triggers cannot be saved through it.** `save_graph` ignores `body.triggers` and re-persists `existing_triggers` (`service.py:328-331`). Trigger edits must use the trigger endpoints.

`useAutomationDraft` owns a serialized queue: at most one request in flight; a structural flush drains and supersedes pending node patches for the same nodes; the local graph is optimistic and reconciled from each response.

### 7.2 The blocker: every write validates the whole graph

`update_node` (`service.py:364`) and `save_graph` (`service.py:329`) both call `validate_graph`, which runs `ActionNodeValidationPolicy` → `SkillActionValidator`, which rejects any config missing a required argument (`validation.py:195-199`). So the moment a user inserts a step — before typing anything into it — **autosave would 422**. Autosave is impossible without a validation mode.

Add an internal mode. No API surface change; no request field:

```python
# api/src/automations/validation.py
class GraphValidationMode(str, Enum):
    DRAFT = "draft"      # structure only
    STRICT = "strict"    # structure + node config semantics


class AutomationGraphValidator:
    def validate(self, nodes, edges, triggers, user_email, automation_id=None,
                 mode: GraphValidationMode = GraphValidationMode.STRICT) -> None:
        node_by_id = self._validate_identity(nodes, edges, triggers)
        start_nodes = self._validate_required_boundaries(nodes)
        outgoing = self._validate_edges(edges, node_by_id)
        for trigger in triggers:
            self._validate_trigger(nodes, trigger)
        self._validate_start_trigger_coverage(start_nodes, triggers)
        entry_node_ids = {t.entry_node_id for t in triggers} or {n.node_id for n in start_nodes}
        self._validate_reachability(nodes, entry_node_ids, outgoing)
        self._reject_cycles(entry_node_ids, outgoing)
        if mode is GraphValidationMode.DRAFT:
            return
        for node in nodes:
            ...  # unchanged per-node policy dispatch
```

Draft mode keeps every structural invariant — unique ids, start/final presence, edge endpoints, trigger references, reachability, acyclicity — and defers only *config semantics*. The chain editor satisfies all structural rules by construction, so draft saves succeed while a step is half-configured.

**Which mode each caller uses:**

```python
# api/src/automations/service.py
def _save_mode(self, automation: Automation) -> GraphValidationMode:
    # An ACTIVE automation can fire from a schedule at any moment, so it must
    # never be editable into an invalid state. Drafts and disabled automations may.
    return (
        GraphValidationMode.STRICT
        if automation.status == AutomationStatus.ACTIVE
        else GraphValidationMode.DRAFT
    )
```

- `save_graph`, `update_node`, `add_node`, `add_edge`, `update_edge`, `delete_edge`, `delete_node` → `_save_mode(automation)`
- `_apply_status_update` → `ACTIVE` → **STRICT** (unchanged, `service.py:205-213`)
- `router.test_run` → **STRICT** (unchanged, `router.py:431`)

This matches n8n and Atlassian: a draft may be broken, a live rule may not. Editing an active automation still validates strictly on every keystroke-save, so the UI must surface those 422s inline — and the status chip should suggest switching to Disabled for heavy restructuring.

## 8. Backend Changes

### 8.1 Node aliases and smart values

Implement [LLD-automation-smart-values](./LLD-automation-smart-values.md) as written. It is already specified in full; the deltas this redesign imposes:

1. **The preview endpoint becomes required, not optional.** Token chips and typeahead sample values need resolved values:
   `POST /{automation_id}/smart-values/preview` → `{ template, context: "latest_run" }` → `{ rendered, tokens[] }`.
2. **`GET /{automation_id}/smart-values` is not needed.** The catalog is computed client-side from the graph plus the selected run's context — the frontend already has both, and it keeps the catalog in sync with unsaved edits.
3. **Alias backfill runs in `save_graph` and `update_node`**, so existing automations acquire aliases on first edit without a migration job. Slug from `name`, deduplicate with `_2`, `_3`, reject reserved words.
4. **`last` resolves from `context.execution.last_step_alias`**, not graph order — branch lanes skip nodes.

Touch list: `models.py` (`alias` on `AutomationNode`, `AutomationNodeResponse`, `Create/UpdateAutomationNodeRequest`, Dynamo (de)serialization), new `api/src/automations/smart_values.py`, `runner.py` (`_render_template`, `_render_smart_values`, `_evaluate_condition`, `_store_context_node` — takes the node, not just the id), `validation.py` (alias format/uniqueness/reserved), `router.py` (preview route), `spa/src/types/automation.ts`.

### 8.2 Trigger forms

`triggers/schemas.py` builds forms for `manual` and `schedule` only, and both expose an `entry_node_id` select — meaningless in a single-start chain. Changes:

- Drop `entry_node_id` from both forms when the graph has exactly one start node; the WHEN card supplies it implicitly.
- Keep the cron `SmartSuggestionConfig` — the "describe it in words" affordance is a genuine asset and belongs on the WHEN card.
- Do **not** add a webhook form (§Non-Goals). The WHEN card's type picker offers Manual and Schedule; webhook is absent, not disabled.

### 8.3 Nothing else

No changes to the runner's execution semantics, the repository, the run model, or the marketplace publish/import paths. `PUT /{id}/graph` and the per-node endpoints already exist and suffice.

## 9. Implementation Plan

**Phase 1 — Backend foundation** (unblocks autosave and readable tokens)
1. `GraphValidationMode` + `_save_mode`, plus tests that a draft graph with an unconfigured action saves and that an active one does not (`api/tests/test_automations_service_validation.py`).
2. `alias` on the node model, requests, responses, Dynamo round-trip; backfill in `save_graph` / `update_node`; alias validation.
3. `smart_values.py` resolver; wire `runner.py` rendering and condition evaluation through it; `context.steps[alias]` + `context.execution` in `_store_context_node`; legacy `$.`/`nodes.<uuid>` paths keep resolving.
4. `POST /{id}/smart-values/preview`.
5. Trigger form cleanup (§8.2).
6. `cd api && uv run pytest -v`.

**Phase 2 — Chain core** (pure, fully testable, no UI)
7. `chainModel.ts` — types, `topoOrder`, `descendants`, `findJoin`, `linearize`.
8. `chainOperations.ts` — insert / delete-with-reconnect / move / convert / setAction / setLaneStops.
9. `chainValidation.ts`, `actionSummary.ts`, `smartValues.ts` (catalog, token parse, insert).
10. Unit tests for all of the above, including the legacy-graph fallback.

**Phase 3 — Workspace shell**
11. `useAutomationDraft` (optimistic graph + serialized autosave queue + save state).
12. `WorkspaceTopBar`, `AutomationWorkspacePage`, `ChainColumn`, `EndCard`, `InsertAffordance`.
13. Route collapse + redirects; strip `AutomationDetailLayout` header; delete `AutomationSideNav`.

**Phase 4 — Cards**
14. `StepCard` (identity + `SchemaForm` params + `StepDataPanel`).
15. `AddStepPalette` with inline install-form handling.
16. `TriggerCard` over the trigger forms.
17. `ConditionCard` + `BranchLane` + `StopCard` + `ConditionBuilder`.

**Phase 5 — Smart values in forms**
18. `SmartValueControl` + `SmartValueTextField`; dispatch on `attr.smart_values` in `FormField.tsx`; emit `smart_values` on skill `action_form` text fields.
19. Token chips with preview-endpoint resolution; `⟨ insert ⟩` on output-tree leaves.

**Phase 6 — Runs and test**
20. `RunsDrawer` (list, pagination, run selection, analytics tab) reusing `AutomationRunsPage` internals and `runDisplay.ts`.
21. Run-view hydration of step cards.
22. `TestPanel` with the generated manual-input form.

**Phase 7 — Cleanup**
23. Delete `AutomationBuilderPage.tsx`, `AutomationRunsPage.tsx`, `AutomationTriggersPage.tsx`; drop the canvas CSS from `styles.css`; remove `@xyflow/react` if no other page uses it.
24. `cd spa && yarn lint && yarn build`.
25. Update `AGENTS.md` doc index and mark the two superseded SPA LLDs accordingly.

Phases 1 and 2 are independent and can run in parallel. Phase 3 depends on both.

## 10. Test Plan

**Backend** (`api/tests/`)
- Draft mode saves a graph whose action node has no arguments; strict mode rejects it.
- An `ACTIVE` automation rejects a config-invalid save; a `DRAFT` one accepts it.
- Draft mode still rejects: duplicate node ids, missing final node, dangling edge endpoints, unreachable nodes, cycles, trigger pointing at a non-start node.
- Alias slugging, duplicate suffixing, reserved-word rejection, backfill on save of an alias-less legacy graph.
- `{{ $.input.input }}`, `{{ input.input }}`, `{{ steps.<alias>.output.response_text }}`, `{{ last.output.response_text }}` all render; conditions resolve aliases; context carries both `nodes` and `steps`.
- Preview endpoint returns per-token status against the latest run.

**Frontend** (new unit tests for `chain/`)
- `linearize` on: linear 3-step graph; condition with rejoining lanes; condition with a lane straight to final (`stops: true`); nested conditions; a fan-out graph → `unsupported` populated.
- `findJoin` picks the earliest shared descendant.
- `insertStep` mid-chain rewires rather than appends; inserting into a `true` lane targets the right edge label.
- `deleteStep` reconnects predecessor to successor (the current-bug regression test).
- `convertStepType` action→condition produces distinct `true`/`false` edges; condition→action collapses to one `next`.
- Round-trip: `linearize(graphAfterOp)` yields the intended chain for every operation.
- `chainValidation` flags a missing required argument.
- Condition expression compile/parse round-trip; unparseable input falls back to raw.
- Smart-value catalog excludes the current step and any step after it in the chain.
- Token parser flags unknown aliases and malformed `{{`.
- Test-input scanner derives fields from `{{ input.x }}` tokens across configs.

**Manual**
1. Create an automation → workspace shows WHEN (Manual) / END only.
2. `⊕` → palette → search "gmail" → pick an action needing setup → fill install form in-card → parameters appear.
3. Type in a parameter; confirm `Saving… → Saved` and that a reload preserves it.
4. Add an agent step; press `{{` in the prompt; insert the Gmail step's output; confirm an alias token, not a UUID.
5. Test run with the generated input form; watch statuses land on the cards; open the Gmail card's Data section and insert a nested output leaf into the agent prompt.
6. Insert an `IF` between two steps; set the false lane to Stop; confirm the edge targets Done and the chain renders `⊘`.
7. Delete a middle step; confirm the chain reconnects and saving succeeds.
8. Activate; confirm a config-incomplete step blocks activation with a readable message; fix and activate.
9. Edit an active automation's step; confirm strict validation errors surface inline.
10. Open `/dashboard/automations/:id/runs` → redirected to `?panel=runs`; select an old run → cards show that run's data.
11. Load a legacy graph built on the old canvas with a fan-out → read-only banner plus JSON fallback, no data loss.

## 11. Migration and Compatibility

- **Existing graphs**: any graph the old builder could produce is a single spine plus condition lanes, so it linearizes. Positions are ignored; aliases backfill on first save. No data migration job.
- **Non-canonical graphs** (hand-crafted via the unused edge endpoints, or marketplace imports with fan-out): `unsupported` is non-empty → the workspace renders read-only with a banner, the raw JSON editor, and an explicit "this workflow uses a shape the linear editor cannot express" message. Never silently rewrite a user's graph.
- **Templates using `{{ $.nodes.<uuid>… }}`** keep resolving; the smart-values resolver retains the legacy path (§8.1).
- **Marketplace publish/import** is untouched: it reads nodes/edges/skills and the `{{ inputs.x }}` convention, none of which change.
- **Deep links** to `/triggers`, `/runs`, `/analytics` redirect into panel state.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Draft mode lets invalid graphs persist | Structural invariants still enforced; activate and test-run stay strict; active automations validate strictly on every save |
| Autosave races with structural saves | Single serialized queue; structural flush supersedes pending node patches; optimistic state reconciled from each response |
| Partial `PUT /graph` payload triggers skill-delete lifecycle | Persist layer always sends the complete node/edge set; assert non-empty before sending |
| Losing the canvas hurts users with complex graphs | Branch lanes cover the representable cases; read-only fallback for the rest; a canvas *view* can return later as a read-only overview without re-entering the edit path |
| Alias rename breaks saved templates | Reference scanner + rename warning, per the smart-values LLD |
| One giant page becomes slow with many steps | Cards are accordion-collapsed by default; run data loads per expanded card; drawer paginates |
| Deleting a condition discards lane steps | Confirmation naming the step count; the operation is a single structural save, so undo = reload before the next save |

## 13. Open Questions

1. Should activation be allowed while client-side issues exist, relying on the backend 422, or should the UI pre-block it? Proposal: allow the attempt — the backend message is more accurate than the client mirror.
2. Should `⊘ Stop` also be offered on the main spine (early exit outside a branch)? Representable as an edge to `final`, but it makes the spine's tail ambiguous. Proposal: branch lanes only for now.
3. Should the runs drawer get live run-progress without SSE by polling the *list* endpoint while a run is active? Cheap, and it makes the rail feel live. Proposal: yes, poll only while a run is non-terminal.
4. Do we want a read-only canvas overview (a "map" popover) for orientation on long chains? Would keep `@xyflow/react`. Proposal: defer; revisit after user feedback.
