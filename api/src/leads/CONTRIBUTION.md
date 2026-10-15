# Leads Contribution Guide

`src/leads/` owns the account's lead forms, its lead statuses and the captures its agents make. Agents capture only
through the `lead_capture` skill, which calls `LeadsService` in process; there is no capture route on `/leads`, the
widget API or `/v1`. Design: `docs/LLD-lead-capture.md` (slice 1) and `docs/LLD-leads-platform.md` (the product).

## Layout

```text
src/leads/
  models.py      LeadForm (and the visitor-safe form profile), LeadSettings and statuses, Capture, capture_id_for
  service.py     LeadsService: forms, statuses, capture (validate, count, save), list and read with plan locking
  repository.py  LeadsRepository: every DynamoDB access; the key structure is in its docstring
  router.py      /leads: forms, settings, usage, captures (admins; members may only list forms)
  errors.py      LeadsError(code, message, status), rendered by the handler in src/exceptions.py
```

## Rules that keep it correct

- **A lead form is the platform form schema.** `form_inputs` are `form_models.FormInput`, checked by
  `visitor_input` (what visitors may see, plus lead defaults) and validated with `form_validation.validate_submission`.
  Don't add a lead-specific field type; extend `form_models` so every form gains it.
- **Slugs never change.** Agent instructions and blueprints name forms by slug (`{{ lead_form:<slug> }}`). Rename
  with `name`; retire with archive.
- **The account comes from the run, never from arguments.** `CaptureOrigin` is built from the skill's runtime
  context.
- **Captures are idempotent by content.** `capture_id_for` hashes account, form, person and answers (not the
  conversation, so a lead can be gathered over several visits). The `CaptureId#` guard is the real check; the
  read-first lookup only spares a write.
- **Form edits update fields in place** (`update_form`), because the capture transaction keeps `capture_count`.
- **Plan locking is computed, not stored.** A capture keeps `month_seq`; `Capture.is_locked(limit)` decides with the
  current plan, so an upgrade unlocks at once. Test captures (`source=dashboard`) have no `month_seq`.
- **Permissions.** `leads:ListForms` (members), `leads:ManageForms`, `leads:ManageSettings`, `leads:ViewCaptures`,
  `leads:ManageCaptures` (admins), all on the account. They are deliberately not `List`/`Describe`, which the member
  and view-only wildcards grant.

## Testing

```bash
uv run pytest tests/test_leads_service.py tests/test_leads_routes.py tests/test_migrate_leads_to_captures.py -q
uv run ruff check src/leads && uv run mypy src/leads
```
