# Low Level Design: Automation Marketplace

Date: 2026-07-02  
Status: Draft  
Owner: InnomightLabs API / SPA

## Summary

Add an Automation Marketplace where users can publish reusable automation templates, browse templates shared by other users, inspect the workflow graph and required skills/actions, provide their own required configuration during import, and create a private automation copy in their account.

The design mirrors Agent Marketplace where possible:

- Publishing creates a versioned marketplace template from an existing user-owned automation.
- Importing creates a new private `Automation` graph owned by the importing user.
- Skill secrets and user credentials are never copied from the publisher.
- Required skill/action configuration is collected from the importing user before the automation is created.
- Imported automations behave like normal automations after import.

## Current Architecture Fit

Existing automation foundations:

- Core models: `api/src/automations/models.py`
  - `Automation`
  - `AutomationNode`
  - `AutomationEdge`
  - `AutomationSkill`
  - `SkillActionConfig`
  - `InvokeAgentActionConfig`
- Persistence: `api/src/automations/repository.py`
  - `save_automation(...)`
  - `save_graph(...)`
  - `get_graph(...)`
  - automation-owned skills, runs, and graph records
- Business logic: `api/src/automations/service.py`
  - `create_automation(...)`
  - `save_graph(...)`
  - `validate_graph(...)`
  - `enable_skill(...)`
  - `list_action_catalog(...)`
- Runner: `api/src/automations/runner.py`
  - executes automation graphs and skill actions
- SPA:
  - `spa/src/pages/dashboard/automations/AutomationsListPage.tsx`
  - `spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx`
  - `spa/src/services/automations/AutomationApiService.ts`
  - `spa/src/types/automation.ts`

Existing marketplace foundations to reuse:

- `api/src/agent_marketplace/`
- `spa/src/pages/dashboard/agent-marketplace/`
- `SkillService.get_install_schema(...)`
- `SkillService.validate_install_config(...)`
- Schema-driven forms through `SchemaForm`

No new runtime is needed after import. The imported automation is a normal automation graph with installed skills. Triggers are intentionally not included in marketplace templates.

## UX

On the Automations list page:

- Keep `Create Automation`.
- Add a sibling `Marketplace` button.
- Clicking `Marketplace` opens an Automation Marketplace page with:
  - Search bar.
  - Marketplace automation cards.
  - Publisher, tags, import count, version.
  - Summary of required skills and workflow steps.

Template detail page:

- Shows title, publisher, description, version, tags, and import count.
- Shows read-only workflow summary:
  - Nodes.
  - Edges.
  - Skills/actions used by action nodes.
- Shows required user-provided configuration:
  - Skill install forms.
  - Action argument template inputs.
- Provides `Import Automation`.

Import flow:

1. User opens a marketplace automation.
2. User reviews the workflow graph and required configuration.
3. User clicks `Import Automation`.
4. SPA fetches import plan.
5. SPA renders:
   - Automation title input.
   - Automation description input.
   - One skill install form per template skill that needs user config.
   - One action-argument form per template action variable that must be filled by the importing user.
6. API validates all submitted configs before writing any records.
7. API creates the automation, installs skills, rewrites node configs to the imported skill ids, regenerates node/edge ids, and saves the graph.
8. User is redirected to the imported automation builder.

## Data Model

Add a domain under:

- `api/src/automation_marketplace/models.py`
- `api/src/automation_marketplace/repository.py`
- `api/src/automation_marketplace/service.py`
- `api/src/automation_marketplace/router.py`

### Status

```python
class MarketplaceAutomationStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
```

### Template Skill

```python
class MarketplaceAutomationSkillTemplate(BaseModel):
    template_skill_key: str
    skill_id: str
    display_name: str | None = None
    description: str | None = None
    required: bool = True
    enabled_on_import: bool = True
    default_config: dict[str, Any] = Field(default_factory=dict)
```

`template_skill_key` is stable inside the template and is used by action nodes instead of publisher-owned installed skill ids.

### Template Node

```python
class MarketplaceAutomationNodeTemplate(BaseModel):
    node_id: str
    type: AutomationNodeType
    name: str
    description: str | None = None
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
```

Node ids are template-local only. On import, create fresh node ids for the importing user's automation and rewrite every edge through a template-node-id to imported-node-id map. This keeps imports semantically equivalent to creating a new automation instance rather than copying database identities.

### Template Edge

```python
class MarketplaceAutomationEdgeTemplate(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    label: str = "next"
    condition: str | None = None
```

### Action Input Placeholder

Some node action arguments should be filled during import, not hardcoded in the template. Use placeholders in node configs:

```json
{
  "action_type": "skill_action",
  "skill_id": "riot_lol_api_client",
  "installed_skill_id": "{{ skills.riot_api.installed_skill_id }}",
  "action": "get_recent_matches",
  "arguments": {
    "game_name": "{{ import.riot_game_name }}",
    "tag_line": "{{ import.riot_tag_line }}"
  }
}
```

Template metadata declares those import inputs:

```python
class MarketplaceAutomationImportInput(BaseModel):
    input_key: str
    label: str
    description: str | None = None
    required: bool = True
    form_input: dict[str, Any]
```

`form_input` follows the existing `FormInput` schema shape so the SPA can render it through `SchemaForm`.

### Template Entity

```python
class MarketplaceAutomationTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: f"automation_template_{uuid4()}")
    title: str
    slug: str = ""
    template_version: int = 1
    parent_template_id: str | None = None
    latest_template_id: str | None = None
    changelog: str | None = None
    short_description: str
    full_description: str
    automation_title: str
    automation_description: str | None = None
    nodes: list[MarketplaceAutomationNodeTemplate] = Field(default_factory=list)
    edges: list[MarketplaceAutomationEdgeTemplate] = Field(default_factory=list)
    skills: list[MarketplaceAutomationSkillTemplate] = Field(default_factory=list)
    import_inputs: list[MarketplaceAutomationImportInput] = Field(default_factory=list)
    source_automation_id: str | None = None
    publisher_user_email: str | None = None
    publisher_display_name: str = "InnomightLabs"
    tags: list[str] = Field(default_factory=list)
    status: MarketplaceAutomationStatus = MarketplaceAutomationStatus.DRAFT
    import_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
```

## DynamoDB Keys

Use the single-table pattern:

```text
PK = MarketplaceAutomation
SK = Template#{template_id}
entity_type = MarketplaceAutomationTemplate
```

Recommended indexes:

```text
GSI1PK = MarketplaceAutomation#Status#{status}
GSI1SK = Rank#{padded_import_count}#Created#{created_at}#Title#{normalized_title}

GSI2PK = User#{publisher_user_email}
GSI2SK = MarketplaceAutomation#{parent_template_id}#Version#{template_version}
```

Search/ranking:

1. import count descending
2. recency descending
3. title alphabetically

This matches the Agent Marketplace decision.

## Publishing

Publishing should support users immediately.

Endpoint:

```http
POST /automation-marketplace/automations/publish
```

Request:

```json
{
  "automation_id": "automation_...",
  "title": "League Match Report Workflow",
  "short_description": "Generate League insights reports from Riot data.",
  "full_description": "This workflow fetches recent match data, generates an HTML report, and stores it as an artifact.",
  "tags": ["league-of-legends", "reports", "gaming"],
  "included_skill_ids": ["riot_lol_api_client", "upload_file"],
  "included_node_ids": ["start", "fetch_recent_matches", "generate_report", "save_artifact", "done"],
  "included_edge_ids": ["edge_start_fetch", "edge_fetch_report", "edge_report_save", "edge_save_done"],
  "import_inputs": [
    {
      "input_key": "riot_game_name",
      "label": "Riot game name",
      "form_input": {"input_type": "text", "name": "riot_game_name", "label": "Riot game name"}
    }
  ],
  "changelog": "Initial version",
  "status": "published"
}
```

Publishing service responsibilities:

1. Load automation graph under publisher.
2. Load automation skills under the automation.
3. Require the publisher to explicitly choose the nodes, edges, skills, and import inputs included in the template.
4. Validate that every included edge references included nodes.
5. Convert installed skill references into stable `template_skill_key` references.
6. Strip encrypted secrets and publisher-specific config from template skills.
7. Preserve safe defaults only.
8. Convert selected graph nodes and edges into template shapes.
9. Require import inputs for any template placeholders.
10. Validate the selected template graph through the same graph validation rules where possible.
11. Save as a new version if the source automation was already published.

### Secret Safety

Do not publish:

- `AutomationSkill.encrypted_secrets`
- Secret config fields.
- OAuth tokens.
- Webhook trigger token hashes.
- User-specific API keys.
- Automation triggers of any type.

Published template skill defaults can include:

- Region defaults.
- Queue ids.
- Non-secret mode flags.
- Report style choices.

## Import Plan

Endpoint:

```http
GET /automation-marketplace/automations/{template_id}/import-plan
```

Response:

```json
{
  "template_id": "automation_template_...",
  "automation": {
    "default_title": "League Match Report Workflow",
    "description": "Generate League insights reports from Riot data.",
    "node_count": 5
  },
  "skill_forms": [
    {
      "template_skill_key": "riot_api",
      "skill_id": "riot_lol_api_client",
      "skill_name": "Riot LOL API Client",
      "required": true,
      "form": {}
    }
  ],
  "input_form": {
    "form_name": "Automation Inputs",
    "form_inputs": []
  }
}
```

Import plan generation responsibilities:

- Build skill install schemas through `SkillService.get_install_schema(...)`.
- Include import input form from template `import_inputs`.
- Do not expose publisher secrets or config.

## Import

Endpoint:

```http
POST /automation-marketplace/automations/{template_id}/import
```

Request:

```json
{
  "title": "My League Report Workflow",
  "description": "Daily ranked report for my account.",
  "skill_configs": {
    "riot_api": {
      "riot_api_key": "RGAPI-...",
      "default_routing_region": "europe",
      "default_platform_region": "euw1"
    }
  },
  "import_inputs": {
    "riot_game_name": "Demon Simon",
    "riot_tag_line": "messi"
  }
}
```

Response:

```json
{
  "automation_id": "automation_...",
  "title": "My League Report Workflow",
  "installed_skills": [
    {
      "template_skill_key": "riot_api",
      "installed_skill_id": "riot_lol_api_client",
      "skill_id": "riot_lol_api_client"
    }
  ],
  "node_count": 5,
  "edge_count": 4
}
```

Import service responsibilities:

1. Load latest published template.
2. Validate all required skill configs using skill install validation before writing.
3. Validate import inputs against the declared input form.
4. Create the automation as `draft` under the importing user without creating default triggers. Do not call the current `create_automation(...)` helper unless the import service removes the helper-created manual trigger before returning.
5. Enable/install required automation skills on the new automation.
6. Build a `template_skill_key -> installed_skill_id` map.
7. Build a `template_node_id -> imported_node_id` map.
8. Render placeholders in node configs using:
   - imported skill ids
   - import inputs
   - safe template defaults
9. Create imported nodes with fresh node ids under the new automation id.
10. Rewrite all edges through the node id map and create fresh edge ids.
11. Validate graph.
12. Save graph.
13. Increment template import count.
14. Roll back created automation/skills/graph records on failure.

## Placeholder Rendering

Add a small, deterministic renderer owned by `automation_marketplace`.

Supported placeholders:

```text
{{ skills.<template_skill_key>.installed_skill_id }}
{{ inputs.<input_key> }}
```

Do not allow arbitrary Jinja execution. This should be a bounded resolver, not a template language.

If a placeholder cannot be resolved, import fails before graph persistence.

## Skill And Action Handling

Skill action nodes use `SkillActionConfig`:

```python
class SkillActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.SKILL_ACTION
    skill_id: str | None = None
    installed_skill_id: str | None = None
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    async_: bool = Field(default=False, alias="async")
```

Template conversion rules:

- Preserve `skill_id`.
- Replace publisher `installed_skill_id` with `{{ skills.<template_skill_key>.installed_skill_id }}`.
- Preserve action name.
- Preserve safe arguments.
- Replace user-specific arguments with `{{ inputs.<input_key> }}` placeholders.

During import:

- Install skills first.
- Resolve installed skill ids.
- Replace placeholders.
- Validate graph with resolved action configs.

## Trigger Handling

Triggers are not part of Automation Marketplace templates in v1.

Rationale:

- Triggers represent deployment/runtime wiring, not the reusable workflow itself.
- Schedule triggers can create recurring cost or unexpected execution.
- Webhook triggers require newly generated secrets and external setup.
- Manual triggers can be added by the user from the normal Triggers page after import.

Import behavior:

- Publish never stores triggers.
- Import never creates triggers from the template.
- The imported automation starts as a draft graph.
- The user can add manual, schedule, or webhook triggers from the normal Triggers page after import.

## Versioning

Automation templates should support versioning in v1.

Publishing behavior:

- First publish creates `template_version = 1`.
- Publishing the same source automation again creates a new template row with:
  - same `parent_template_id`
  - incremented `template_version`
  - `latest_template_id` pointing to the newest version
- Older versions remain readable if referenced, but listing should show latest published versions only.

Imported automations do not auto-update when a template changes.

## API Contract

Router:

```python
router = APIRouter(prefix="/automation-marketplace", tags=["automation-marketplace"])
```

Endpoints:

```http
GET /automation-marketplace/automations?query=&limit=20
GET /automation-marketplace/automations/{template_id}
GET /automation-marketplace/automations/{template_id}/import-plan
POST /automation-marketplace/automations/{template_id}/import
POST /automation-marketplace/automations/publish
POST /automation-marketplace/automations/{template_id}/archive
```

Visibility:

- Public list/detail/import endpoints show only `published` templates.
- Publish/archive endpoints require the authenticated owner.

## Frontend Plan

Add:

- `spa/src/pages/dashboard/automation-marketplace/AutomationMarketplacePage.tsx`
- `spa/src/pages/dashboard/automation-marketplace/AutomationMarketplaceDetail.tsx`
- `spa/src/services/automationMarketplace/AutomationMarketplaceApiService.ts`
- `spa/src/types/automationMarketplace.ts`

Routes:

```tsx
<Route path="automations/marketplace" element={<AutomationMarketplacePage />} />
<Route path="automations/marketplace/:templateId" element={<AutomationMarketplaceDetail />} />
```

Update:

- `spa/src/pages/dashboard/automations/AutomationsListPage.tsx`
  - Add `Marketplace` button next to `Create Automation`.

Marketplace list UI:

- Search input.
- Template cards.
- Publisher, tags, import count, version.
- Node count, edge count, skill count.

Detail/import UI:

- Main area:
  - Overview.
  - Read-only graph summary.
  - Required inputs.
  - Included skills.
- Side panel:
  - Import button.
  - Version/import metadata.
- Import modal:
  - Automation title/description fields.
  - Skill install forms grouped by skill.
  - Import input form.

Use existing `SchemaForm` for skill and import-input forms. Avoid one giant flattened form so field names do not collide.

## Security

- Never copy publisher skill secrets.
- Never copy webhook token hashes.
- Always create imported automations under the importing user.
- Always import as `draft` by default.
- Never publish or import automation triggers.
- Validate all skill configs before writing.
- Validate graph after placeholder resolution.
- Do not execute imported automations during import.
- Keep OAuth skills installed disabled until the user connects/enables them if the existing skill behavior requires it.

## Tests

API tests:

- List returns latest published automation templates only.
- Detail rejects draft/archived templates.
- Publish creates version 1 from a user-owned automation graph.
- Re-publish creates a new version and updates latest pointer.
- Publish strips secrets and webhook token hashes.
- Publish excludes triggers.
- Publish only includes explicitly selected nodes, edges, skills, and import inputs.
- Import plan returns skill install forms and import input form.
- Import rejects missing required skill config.
- Import rejects unresolved placeholders.
- Import creates automation under importing user.
- Import installs skills using importing user's config.
- Import rewrites node configs from template skill keys to imported installed skill ids.
- Import regenerates node ids and rewrites edges to the new node ids.
- Import does not create triggers.
- Failed import rolls back automation and installed skills.

SPA tests/manual checks:

- Automations page shows `Marketplace`.
- Marketplace list loads/searches templates.
- Detail page shows graph summary and required setup.
- Import flow renders grouped forms.
- Successful import navigates to `/dashboard/automations/{automation_id}/builder`.

## Implementation Steps

1. Add automation marketplace models.
2. Add repository with latest-published listing, detail lookup, save, import-count increment, and source automation version lookup.
3. Add bounded placeholder resolver.
4. Add publish service that converts an automation graph into a secret-safe template.
5. Add import-plan service.
6. Add import service with pre-validation, skill installation, placeholder rendering, node/edge id rewriting, graph save, and rollback.
7. Add router endpoints.
8. Register router in FastAPI app.
9. Add API tests.
10. Add SPA service/types/routes.
11. Add Automations page `Marketplace` button.
12. Add marketplace list/detail/import pages.
13. Run:

```bash
cd api
uv run pytest -v
cd ../spa
yarn build
```

## Resolved Decisions

1. Triggers are not included in marketplace templates. Users add triggers from the normal automation Triggers page after import.
2. The publisher explicitly chooses what to export: nodes, edges, skills, and import inputs. The platform validates that selected edges reference selected nodes and that placeholders are declared.
3. Import creates a fresh automation instance by generating new node ids, generating new edge ids, and rewriting edge source/target ids through a template-node-id to imported-node-id map.
