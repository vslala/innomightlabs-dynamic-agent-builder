# Agent Marketplace Contribution Guide

`src/agent_marketplace/` publishes an agent as a global, versioned template and imports a template as a new agent in
the importer's account, installing its skills. It is the simpler sibling of `src/automation_marketplace/` and depends on
`src/agents/` and `src/skills/`.

## Layout

```text
src/agent_marketplace/
  __init__.py    re-exports `router`
  router.py      /agent-marketplace routes: list, detail, import-plan, import, publish, archive
  service.py     AgentMarketplaceService: publish/version, import with rollback, skill config validation
  repository.py  AgentMarketplaceRepository: template storage, listing, ranking, search
  models.py      MarketplaceAgentTemplate, skill templates, request/response schemas
```

## Conventions

- **Keys.** Global partition: `pk=MarketplaceAgent`, `sk=Template#{template_id}`. There is no GSI; listing queries the
  partition and filters in Python (status, latest version, text query), ranked by `-import_count`, newest, then title.
  `limit` is clamped to 1..50.
- **Versions.** Publishing the same `source_agent_id` by the same publisher creates a new template with
  `template_version + 1` and the same `parent_template_id`; the previous latest gets `latest_template_id` updated.
- **Access.** Import checks `agents:Create` on `ResourceRef("agent")`; publish checks `agents:Share` via
  `require_agent` and then the service also demands `agent.owner_id == owner.user_id`; archive is publisher-only.
  `Owner` is injected with `Depends(get_owner)`, `Principal` with `Depends(get_principal)`.
- **Errors.** The service raises `ValueError`; the router maps it to 404 (read, archive), 400 (import, publish).
- **Secrets.** `_safe_default_config` drops every `secret_fields` entry of an installed skill before it is stored in
  the template. Skills that need OAuth are marked `enabled_on_import=False`.
- **Import is all or nothing.** The agent is saved first; if any skill install fails, installed skills are uninstalled
  and the agent is deleted, then the error is re-raised. Provider/model overrides are honoured only when the template has
  `allow_model_override`, and always go through `validate_provider_model`.

## How to add a field to a template

1. Add it to `MarketplaceAgentTemplate` and both `to_dynamo_item` / `from_dynamo_item` in `models.py` (give it a default so
   existing items still load).
2. Fill it in `publish_agent`; use it in `import_agent`.
3. Add it to the summary/detail response if the SPA shows it.
4. Extend `tests/test_agent_marketplace.py`.

## Testing

```bash
uv run pytest tests/test_agent_marketplace.py -q
uv run ruff check src/agent_marketplace && uv run mypy src/agent_marketplace
```

Fixtures: `test_client`, `auth_headers`, `dynamodb_table` (moto). See `test_marketplace_publish_import_and_secret_stripping`
and `test_marketplace_import_installs_oauth_skill_disabled_without_connection`.

## Do / Don't

- Do strip secrets at publish time and test it; don't store a skill config you did not filter.
- Do keep the rollback in `import_agent` when adding steps that create resources.
- Do put validation in the service and HTTP mapping in the router.
- Don't add GSIs or a search service for the marketplace until the listing is actually too slow.
- Don't import into an account without `agents:Create`; the new agent is owned by the importer.
