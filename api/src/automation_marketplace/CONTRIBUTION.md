# Automation Marketplace Contribution Guide

`src/automation_marketplace/` lets a member publish one of their automations as a global, versioned template and lets
others import a template as a new draft automation in their own account. Templates are stripped of anything that belongs
to the publisher (agent ids, skill config, owner-scoped values) and replaced by placeholders the importer fills in.
It builds on `src/automations/` and `src/skills/`; its sibling for agents is `src/agent_marketplace/`.

## Layout

```text
src/automation_marketplace/
  router.py        /automation-marketplace routes: list, detail, import-plan, import-session, import, publish, archive
  service.py       AutomationMarketplaceService: publish/version, import with rollback, import sessions, placeholder checks
  repository.py    AutomationMarketplaceRepository: templates and import sessions
  models.py        MarketplaceAutomationTemplate, ImportSession (with TTL), request/response schemas
  placeholders.py  MarketplacePlaceholderRenderer: resolves {{ skills.<key>.<field> }} and {{ inputs.<key> }}
```

## Conventions

- **Keys.** Templates are global: `pk=MarketplaceAutomation`, `sk=Template#{template_id}`, `entity_type=MarketplaceAutomationTemplate`.
  Import sessions are per member: `pk=member_partition(account_id, owner_id)`, `sk=AutomationMarketplaceImportSession#{session_id}`
  with an `expires_at` and a `ttl` (DynamoDB TTL can lag up to 48h, so `is_expired()` is also checked in code).
- **Versions.** Re-publishing the same source automation by the same publisher creates a new template
  (`template_version + 1`, shared `parent_template_id`); `_promote_latest_version` points the old versions'
  `latest_template_id` at the new one. Listings only show the template whose `latest_template_id == template_id`.
- **Access.** Routes are thin. Import requires `automations:Create` on `ResourceRef("automation")`; publish requires
  `automations:Share` on the source automation via `require_automation`. Archive is limited to the publisher
  (`publisher_user_id == owner.user_id`). The owner comes from `get_owner(request)`, the principal from `get_principal(request)`.
- **Errors.** The service raises `ValueError`; the router maps it to 404 (read/archive) or 400 (import/publish).
  Lookups of unpublished or archived templates raise the same "not found" error.
- **Publishing is a sanitising step.** `_publish_node_config` dispatches on action type (a dict of publishers):
  invoke-agent nodes must already use an `{{ inputs.* }}` placeholder for `agent_id`; skill-action nodes get
  `installed_skill_id` rewritten to `{{ skills.<key>.installed_skill_id }}`, and owner-scoped arguments
  (declared in the skill manifest `automation.owner_scoped_arguments`) become `{{ inputs.* }}` plus a generated import input.
  Skill config is never copied. `_validate_placeholders_declared` rejects any input placeholder without a declared import input.
- **Import is all or nothing.** `import_automation` creates a DRAFT automation, installs the template's skills, renders
  the graph, validates it with `AutomationService.validate_graph`, saves nodes and edges (no triggers), and on any
  exception calls `_rollback_import`. Import count is bumped only after success.
- **Forms.** The import plan returns schema-driven forms (`Form`, `FormInput`) for each skill and for import inputs;
  keep input keys stable because saved sessions refer to them.

## How to add support for a new action type in templates

1. Make sure the action type exists in `src/automations` (see its `CONTRIBUTION.md`).
2. Add a `_publish_<type>_config` method in `service.py` and register it in the dict in `_publish_node_config`
   so nothing owner-specific is published.
3. Make the import side render it: `_imported_node` runs the placeholder renderer over the node config; add new
   placeholder sources only in `placeholders.py` (`PLACEHOLDER_RE` and `_resolve`).
4. Cover publish and import in `tests/test_automation_marketplace.py`.

## Testing

```bash
uv run pytest tests/test_automation_marketplace.py -q
uv run ruff check src/automation_marketplace && uv run mypy src/automation_marketplace
```

Tests use moto via `dynamodb_table` (and `test_client`/`auth_headers` for routes) and construct
`AutomationMarketplaceService` with real repositories. Cases to copy: `test_automation_marketplace_publish_never_copies_skill_config`,
`..._republish_creates_new_version`, `..._import_session_persists_with_ttl`.

## Do / Don't

- Do strip publisher data at publish time; don't trust an importer-supplied value to be safe, validate it.
- Do roll back every partial import; don't leave half-created automations or installed skills.
- Do keep new placeholder sources in `placeholders.py`; don't add ad hoc string replacement in the service.
- Don't bypass `automations:Share` on publish or `automations:Create` on import.
- Don't copy ranking or search logic into a third marketplace; the two repositories already duplicate it deliberately
  rather than share an abstraction. Change both if the behaviour must change.
