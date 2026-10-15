# Automations Contribution Guide

`src/automations/` owns automation graphs (start, action, condition and final nodes joined by edges), their triggers
(manual, webhook, schedule, lead captured), per-automation skill installs, and runs. An automation runs as its owner: their agents,
connectors and provider settings. Schedules are delegated to `src/scheduler/`; publishing and importing live in
`src/automation_marketplace/`.

## Layout

```text
src/automations/
  router.py        /automations routes; maps domain errors to HTTP in translate_error()
  dispatch.py      invoke_automation_run_async: start a created run in a local task or the async job Lambda
  access.py        require_automation(), automation_with(action) dependency, visibility, owner_of_automation()
  service.py       AutomationService: CRUD, graph save, status changes, skills, action catalog, smart-value preview
  runner.py        AutomationRunner: executes a graph node by node (start/condition/action executors)
  run_state.py     AutomationRunStateService: run status transitions and heartbeat staleness
  validation.py    AutomationGraphValidator + per-node policies + action config validators
  models.py        Pydantic models: items (to/from_dynamo_item), request and response schemas, enums
  repository.py    AutomationRepository: all DynamoDB access
  smart_values.py  {{ steps.<alias>.output... }} parser/resolver, filters, condition evaluation
  aliases.py       stable node aliases used by smart values; backfilled on every save
  errors.py        AutomationNotFoundError, AutomationValidationError
  triggers/
    models.py      ScheduleTriggerConfig (cron or one-time run_at)
    schemas.py     schema-driven trigger forms (build_schedule_trigger_form, build_manual_trigger_form)
    service.py     AutomationTriggerLifecycleService: mirrors schedule triggers into src/scheduler, lead triggers into the registry
    lead_captured.py  the Lead captured trigger: LeadTriggerRegistry (who listens) and LeadEventDispatcher (the scheduler
                      starts the runs for each captured lead's event, idempotently and with retries; see leads/events.py)
```

## Conventions

- **Split.** Routers parse and authorize, `AutomationService` holds logic, `AutomationRepository` is the only code that
  touches the table, models carry their own keys. Services take their collaborators in `__init__` with a default
  (`repo or AutomationRepository()`) so tests inject fakes.
- **Keys.** The `Automation` item lives in the account partition: `pk=Account#{account_id}`, `sk=Automation#{id}`
  (shareable, listed by prefix). Everything that belongs to one automation sits under `pk=Automation#{id}`:
  `Node#`, `Edge#`, `Trigger#`, `Skill#`, `Run#{created_at}#{run_id}`. A run is also written as a lookup item
  `pk=AutomationRun#{run_id}, sk=Run` (`save_run` writes both) so `find_run_by_id` works without the timestamp;
  node results sit under `AutomationRun#{run_id}` / `NodeResult#`. Webhook triggers add `gsi2_pk=WebhookTrigger#{token_hash}`.
  Keys are `pk`/`sk` properties and `to_dynamo_item` on the model; floats must go through `dynamo_item()`.
- **Access.** Every route reaches its automation with `Depends(automation_with("automations:<Verb>"))`:
  404 when the caller cannot see it, 403 when they can but may not act. Verbs are in `src/iam/actions.py`
  (`Describe`, `Get`, `Update`, `Delete`, `Run`; `Create` is checked inline with `ResourceRef("automation")`).
  Repository `find_in_account` does not authorize. After authorizing, use `owner_of_automation(automation)` so the
  work runs as the owner, not the caller. Sharing roles map to verbs in `src/iam/shares.py`; `access_to()` yields
  `owner`, `shared` or `admin` (metadata only).
- **Errors.** Raise `AutomationNotFoundError` / `AutomationValidationError` (and `SchedulerValidationError` from the
  scheduler); the router converts them via `translate_error` (404, 422, else 500). Do not raise `HTTPException` in the service.
- **Validation modes.** Draft/disabled automations save with `GraphValidationMode.DRAFT` (structure only); active ones
  with `STRICT`, because a schedule can fire at any time. Activation and test runs validate strictly.
- **Node and action kinds.** Node types dispatch through dicts in `AutomationRunner` (`_node_executors`,
  `_action_executors`); validation uses a list of `NodeValidationPolicy` and `ActionConfigValidator` objects wired in
  `AutomationService.__init__`. Extend those lists rather than adding `if` chains.
- **Triggers and schedules.** Saving or activating a schedule trigger calls `sync_trigger`, which creates/updates a
  `src/scheduler` schedule with id `automation:{id}:trigger:{trigger_id}`. A completed one-time schedule is not re-run.
- **Forms.** Trigger forms are built in `triggers/schemas.py` and served at `GET /automations/{id}/triggers/forms/{type}`;
  keep field names stable (the SPA renders them with `SchemaForm`).
- **Run execution.** `POST /{id}/test-run` creates a PENDING run, then `invoke_automation_run_async` (`dispatch.py`) runs it with
  `asyncio.create_task` locally or invokes a Lambda when `ASYNC_JOB_BACKEND=lambda` (`ASYNC_JOB_LAMBDA_NAME`); `runner.py` updates heartbeats through `AutomationRunStateService`,
  and reading a run with an expired heartbeat marks it failed.

## How to add a new action type

1. Add the value to `AutomationActionType` and a config model next to `InvokeAgentActionConfig` in `models.py`.
2. Add an `ActionConfigValidator` in `validation.py` (see `InvokeAgentActionValidator`) and put it in the
   `action_validators` list in `AutomationService.__init__`.
3. Add an `_execute_..._action` method in `runner.py` and register it in `_action_executors`.
4. If the action appears in the picker, extend `list_action_catalog` in `service.py`.
5. Add tests in `tests/test_automations_runner.py` and `tests/test_automations_service_validation.py`.

For a new trigger type, add the enum value, a form builder in `triggers/schemas.py`, a branch in `get_trigger_form`
and `sync_trigger` (only if an external resource needs mirroring).

## Testing

```bash
uv run pytest tests/test_automations_*.py tests/test_automation_access.py -q
uv run ruff check src/automations tests/test_automations_*.py && uv run mypy src/automations
```

Tests use moto through `dynamodb_table`, `test_client`, `auth_headers` and `automation_repository` from
`tests/conftest.py`; request payloads come from `tests/mock_data.py` (`AUTOMATION_CREATE_REQUEST`). Router tests
monkeypatch `invoke_automation_run_async` rather than starting a run.

## Do / Don't

- Do authorize with `automation_with(...)` in every new route; don't call `find_in_account` from a router and stop there.
- Do run work as `owner_of_automation(...)`; don't use the caller's identity for agents or connectors.
- Do keep key shapes in the models; don't build `pk`/`sk` strings in services.
- Do convert errors in `translate_error`; don't leak exceptions as 500s.
- Do keep a run lookup in step with the run item (use `save_run`); don't `put_item` a run directly.
- Don't validate node config strictly on draft saves; the builder autosaves half-finished steps.
- Don't add a new node kind through an `if` chain; extend the executor dict or policy list.
- Comments explain why (see the `_save_mode` docstring); don't narrate what the code does.
