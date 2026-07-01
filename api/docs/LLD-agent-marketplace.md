# Low Level Design: Agent Marketplace

Date: 2026-06-30  
Status: Draft  
Owner: InnomightLabs API / SPA

## Summary

Add an Agent Marketplace where users can browse pre-built agents shared by other users or curated by the platform, inspect formatted read-only agent instructions and attached skills, provide any required skill configuration, and import a private copy into their own account.

Imported agents should behave exactly like normal user-created agents. Marketplace templates are source definitions; importing creates a new `Agent` row owned by the importing user and installs the selected template skills with that user's configuration.

Users should be able to publish their own agents to the marketplace in v1. Publishing exports the agent definition and safe skill metadata, never installed skill secrets or user-owned credentials.

## User Experience

On the dashboard Agents page:

- Keep the existing `Create Agent` button.
- Add a sibling `Marketplace` button.
- Add a `Publish to Marketplace` action on eligible agent detail/settings surfaces.
- Clicking `Marketplace` opens a marketplace section/page with:
  - Search bar.
  - Category/filter controls later.
  - List/grid of marketplace agents.
  - Agent detail preview with:
    - Name/title.
    - Publisher.
    - Description.
    - Full agent instructions/persona.
    - Attached skills and what each skill does.
    - Required import inputs for each skill.
  - `Import Agent` button.

Import flow:

1. User selects a marketplace agent.
2. User reviews agent instructions and attached skills.
3. User clicks `Import Agent`.
4. SPA renders a form for:
   - Imported agent name.
   - Provider/model override fields, defaulted from the template.
   - One install form per skill that requires user configuration.
5. API validates every required skill config before writing anything.
6. API creates a new private agent under the importing user.
7. API installs the template skills on that agent using existing `SkillService.install_skill(...)`.
8. User is redirected to the imported agent detail page.

Publish flow:

1. User opens one of their agents and clicks `Publish to Marketplace`.
2. SPA shows a publish form for title, short description, full description, tags, and included skills.
3. API loads the user's agent and installed skills.
4. API exports only safe template data:
   - Agent architecture/provider/model/persona/description.
   - Skill ids and non-secret safe defaults.
   - Skill display metadata.
5. API creates a published marketplace template immediately.
6. The published template becomes discoverable in marketplace search/list.

## Current Architecture Fit

Existing pieces to reuse:

- Agent creation:
  - `api/src/agents/router.py`
  - `api/src/agents/models.py`
  - `api/src/agents/repository.py`
- Skill catalog and installation:
  - `api/src/skills/router.py`
  - `api/src/skills/service.py`
  - `SkillService.get_install_schema(...)`
  - `SkillService.install_skill(...)`
- Schema-driven forms:
  - `api/src/form_models.py`
  - `spa/src/components/forms/SchemaForm.tsx`
- Agent list UI:
  - `spa/src/pages/dashboard/AgentsList.tsx`
- Agent creation UI:
  - `spa/src/pages/dashboard/AgentCreate.tsx`

No special runtime path is needed after import. The imported agent is just a normal agent with installed skills.

## Data Model

Add a marketplace domain under:

- `api/src/agent_marketplace/models.py`
- `api/src/agent_marketplace/repository.py`
- `api/src/agent_marketplace/service.py`
- `api/src/agent_marketplace/router.py`

### Marketplace Template

```python
class MarketplaceAgentStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MarketplaceAgentSkillTemplate(BaseModel):
    template_skill_key: str
    skill_id: str
    display_name: str | None = None
    description: str | None = None
    required: bool = True
    enabled_on_import: bool = True
    default_config: dict[str, Any] = Field(default_factory=dict)


class MarketplaceAgentTemplate(BaseModel):
    template_id: str
    title: str
    slug: str
    template_version: int = 1
    parent_template_id: str | None = None
    latest_template_id: str | None = None
    changelog: str | None = None
    short_description: str
    full_description: str
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: str
    allow_model_override: bool = True
    agent_persona: str
    agent_description: str
    skills: list[MarketplaceAgentSkillTemplate] = Field(default_factory=list)
    source_agent_id: str | None = None
    publisher_user_email: str | None = None
    publisher_display_name: str = "InnomightLabs"
    tags: list[str] = Field(default_factory=list)
    status: MarketplaceAgentStatus = MarketplaceAgentStatus.DRAFT
    import_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
```

### DynamoDB Keys

Use the existing single-table pattern:

```text
PK = MARKETPLACE#AGENT
SK = TEMPLATE#{template_id}
GSI1PK = MARKETPLACE#AGENT#STATUS#{status}
GSI1SK = RANK#{inverse_import_count}#CREATED#{inverse_created_at}#TITLE#{normalized_title}#TEMPLATE#{template_id}
GSI2PK = USER#{publisher_user_email}
GSI2SK = MARKETPLACE_AGENT#{template_id}
```

For v1, templates can be user-published immediately or curated/admin-seeded. `source_agent_id` is stored for owner traceability and later edit/version flows, but imports still create private copies that do not auto-update when the source template changes.

Marketplace list ranking should be deterministic:

1. Highest `import_count`.
2. Most recent `created_at`.
3. Alphabetical `title`.

Because DynamoDB sorts ascending, the repository should store sortable inverted rank values for import count and created time, or sort the current page in service code if v1 uses a small curated/user-published result set. Prefer repository-level sort keys once the marketplace grows.

## API Contract

Add router prefix:

```python
router = APIRouter(prefix="/agent-marketplace", tags=["agent-marketplace"])
```

Endpoints:

```http
GET /agent-marketplace/agents?query=&limit=20&cursor=
```

Returns published marketplace templates with compact fields.

```http
GET /agent-marketplace/agents/{template_id}
```

Returns full template detail, including full agent instructions and skills.

```http
GET /agent-marketplace/agents/{template_id}/import-plan
```

Returns a renderable import plan:

```json
{
  "template_id": "league-insights-coach",
  "agent": {
    "default_name": "League Insights Coach",
    "default_provider": "openai",
    "default_model": "gpt-4.1-mini",
    "allow_model_override": true,
    "description": "...",
    "persona_preview": "..."
  },
  "skill_forms": [
    {
      "template_skill_key": "riot_api",
      "skill_id": "riot_lol_api_client",
      "skill_name": "Riot LOL API Client",
      "required": true,
      "form": {
        "form_name": "Configure Riot LOL API Client",
        "form_inputs": []
      }
    }
  ]
}
```

```http
POST /agent-marketplace/agents/{template_id}/import
```

Request:

```json
{
  "agent_name": "My League Coach",
  "agent_provider": "openai",
  "agent_model": "gpt-4.1-mini",
  "skill_configs": {
    "riot_api": {
      "riot_api_key": "RGAPI-...",
      "default_platform_region": "euw1",
      "default_routing_region": "europe"
    },
    "report_generator": {
      "report_agent_id": "agent_..."
    }
  }
}
```

Response:

```json
{
  "agent_id": "agent_...",
  "agent_name": "My League Coach",
  "installed_skills": [
    {
      "template_skill_key": "riot_api",
      "installed_skill_id": "riot_lol_api_client",
      "skill_id": "riot_lol_api_client"
    }
  ]
}
```

```http
POST /agent-marketplace/agents/publish
```

Publishes a marketplace template from one of the current user's agents.

Request:

```json
{
  "agent_id": "agent_...",
  "title": "League Insights Coach",
  "short_description": "Analyze recent League games and generate improvement plans.",
  "full_description": "A detailed coach agent for Riot match review, pattern analysis, and report generation.",
  "tags": ["league-of-legends", "gaming", "coaching"],
  "included_skill_ids": ["riot_lol_api_client", "upload_artifact"],
  "status": "published"
}
```

Response:

```json
{
  "template_id": "template_...",
  "status": "published",
  "title": "League Insights Coach"
}
```

Only the agent owner can publish an agent. The service must never copy installed skill secret config into `default_config`.

## Import Service Design

`AgentMarketplaceService.import_agent(...)` should coordinate the import.

Responsibilities:

1. Load published template.
2. Validate requested `agent_name`.
3. Validate provider/model overrides when present.
4. Load each referenced skill manifest.
5. Build an import plan from current skill install schemas.
6. Validate all submitted skill configs before creating the agent.
7. Create the new agent under `request.state.user_email`.
8. Install each template skill with existing `SkillService.install_skill(...)`.
9. Return imported agent details.

Important: validate all configs before the first write. This avoids creating half-imported agents when a skill field is missing or invalid.

Pseudo-code:

```python
def import_agent(template_id: str, user_email: str, request: ImportMarketplaceAgentRequest):
    template = repository.find_published(template_id)
    if not template:
        raise ValueError("Marketplace agent not found")

    skill_inputs = {item.template_skill_key: item for item in template.skills}
    _validate_required_skill_configs(skill_inputs, request.skill_configs)

    for skill in template.skills:
        merged_config = {**skill.default_config, **request.skill_configs.get(skill.template_skill_key, {})}
        skill_service.validate_install_config(skill.skill_id, user_email, merged_config)

    agent_provider = request.agent_provider or template.agent_provider
    agent_model = request.agent_model or template.agent_model
    agent_service.validate_provider_model(agent_provider, agent_model)

    agent = Agent(
        agent_name=request.agent_name or template.agent_name,
        agent_architecture=template.agent_architecture,
        agent_provider=agent_provider,
        agent_model=agent_model,
        agent_persona=template.agent_persona,
        agent_description=template.agent_description,
        created_by=user_email,
    )
    saved_agent = agent_repository.save(agent)

    installed = []
    try:
        for skill in template.skills:
            config = {**skill.default_config, **request.skill_configs.get(skill.template_skill_key, {})}
            installed.append(
                skill_service.install_skill(
                    saved_agent.agent_id,
                    skill.skill_id,
                    user_email,
                    config,
                    enabled=skill.enabled_on_import,
                )
            )
    except Exception:
        # best-effort rollback: uninstall installed skills and delete agent
        rollback_import(saved_agent.agent_id, installed)
        raise

    repository.increment_import_count(template_id)
    return imported_response(saved_agent, installed)
```

Add a `SkillService.validate_install_config(...)` helper so the marketplace service can validate before writing without duplicating private normalization/encryption rules.

Add or reuse an agent provider/model validation helper so marketplace imports can safely override provider/model without duplicating `AgentCreate` validation rules.

### Publish Service Design

`AgentMarketplaceService.publish_agent(...)` should create a marketplace template from a user-owned agent.

Responsibilities:

1. Load the source agent and verify `created_by == user_email`.
2. Load installed skills for that agent.
3. Filter included skills to those installed on the source agent.
4. Export skill ids, display metadata, and safe defaults only.
5. Drop all secret fields and OAuth/token values.
6. Store the template as `PUBLISHED` immediately unless the user explicitly saves a draft.
7. Return the new template id.

Publishing should not mutate the source agent. A later template edit/version flow can update marketplace templates without changing already-imported agents.

## Skill Config Handling

Marketplace templates should not store another user's secrets. Template skill configs may include safe defaults only:

- Region defaults.
- Mode flags.
- Report settings.
- Non-secret labels.

They must not include:

- API keys.
- OAuth tokens.
- User-owned IDs unless explicitly safe.

Secret fields remain handled by existing skill manifests via `attr.secret: "true"` and `SkillService.install_skill(...)`.

OAuth skills:

- OAuth-based skills should be installed disabled on import when they require a user connection.
- The existing disabled-skill helper/note on the agent Skills page should tell the user to enable/connect it; no separate marketplace-specific OAuth flow is required for v1.
- Template publishing must not copy OAuth credential state, access tokens, refresh tokens, or provider account ids from the publisher.

## Frontend Design

Add:

- `spa/src/pages/dashboard/agent-marketplace/AgentMarketplacePage.tsx`
- `spa/src/pages/dashboard/agent-marketplace/MarketplaceAgentDetail.tsx`
- `spa/src/services/agentMarketplace/AgentMarketplaceApiService.ts`
- `spa/src/types/agentMarketplace.ts`

Routes:

```tsx
<Route path="agents/marketplace" element={<AgentMarketplacePage />} />
<Route path="agents/marketplace/:templateId" element={<MarketplaceAgentDetail />} />
```

Update:

- `spa/src/pages/dashboard/AgentsList.tsx`
  - Add `Marketplace` button next to `Create Agent`.

Marketplace list UI:

- Search input.
- Template cards.
- Publisher, tags, short description.
- Attached skill count.

Marketplace detail/import UI:

- Left/main area: description and formatted read-only instructions.
- Right panel: skill list and import button.
- On import:
  - Fetch import plan.
  - Render agent name input.
  - Render provider/model override controls, defaulted from the template.
  - Render one `SchemaForm` per skill form.
  - Submit combined payload.
  - Navigate to `/dashboard/agents/{agent_id}`.

Avoid making one giant flattened form for all skills in v1. Separate skill forms are clearer, avoid field-name collisions, and reuse the existing `SchemaForm` without modifying the form contract.

Instruction rendering:

- Do not show `agent_persona` in a raw editable textarea.
- Render escaped text in a formatted read-only instructions component.
- Preserve paragraphs, lists, and code-like blocks if the persona uses plain text conventions.
- Do not provide a copy button or copy affordance.
- CSS may use `user-select: none` to reduce casual copying, but this is a UX choice, not a security boundary.

Publishing UI:

- Add a publish action from agent detail/settings.
- Show a publish form with title, descriptions, tags, and included installed skills.
- Make secret/OAuth behavior explicit: skill secrets are not published, importers must provide their own config.
- After publish, navigate to the marketplace detail page for the new template.

## Publishing V1

V1 should support immediate user publishing. There is no approval queue in the first implementation.

Rules:

- Users can publish only agents they own.
- Published templates are visible/importable immediately.
- Users can archive their own published templates.
- Admins can archive abusive or broken templates later.
- Publishing exports safe agent and skill metadata only.
- Publishing never exports installed skill secrets, OAuth tokens, generated artifacts, conversations, memories, or user-specific runtime state.

Do not let users publish live skill secrets. Publishing should export agent instructions and skill IDs/defaults only.

## Template Versioning

Versioning is in scope for v1. Editing a published template should create a new template version instead of mutating the existing published definition in place.

```python
template_version: int
parent_template_id: str | None
latest_template_id: str | None
changelog: str | None
```

Rules:

- First publish creates `template_version = 1`.
- Editing a published template creates a new `template_id` with `template_version = previous + 1`.
- `parent_template_id` points to the first version in the lineage.
- `latest_template_id` points to the latest version for convenient navigation.
- Imports should default to the latest published version.
- Existing imported agents should not auto-update when a marketplace template changes. They are private copies.
- Older versions remain retrievable for audit/import history, but marketplace list pages should show only latest published versions by default.

## Security

- Only `PUBLISHED` templates are visible/importable.
- Import always creates an agent owned by the importing user.
- Never copy publisher-owned installed skill config or secrets.
- Validate all skill configs using the current skill manifest before creating the agent.
- Sanitize/escape marketplace descriptions in the SPA. Render markdown only if a safe renderer is introduced.
- Rate-limit imports later if needed.

## Tests

API:

- List returns only published templates.
- List ranks templates by import count, then recency, then title.
- Detail rejects draft/archived templates.
- Publish rejects agents not owned by the current user.
- Publish creates an immediately listable template.
- Publish exports selected installed skills but excludes all secret config fields.
- Editing a published template creates a new version instead of mutating the old version.
- Marketplace list shows the latest published version by default.
- Owner can archive their published template.
- Import plan returns skill install schemas.
- Import rejects missing required skill config.
- Import rejects invalid skill config enum/options.
- Import creates agent under importing user, not publisher.
- Import supports provider/model overrides and validates invalid overrides.
- Import installs skills using submitted user config.
- Import installs OAuth-based skills disabled when they require user connection.
- Secret skill fields are encrypted through existing skill install flow.
- Failed skill install rolls back created agent and any installed skills.

SPA:

- Agents page shows `Marketplace` next to `Create Agent`.
- Agent detail/settings shows `Publish to Marketplace` for owned agents.
- Marketplace search filters or calls API with query.
- Detail page shows description, formatted read-only instructions, and skills.
- Detail page does not show a copy action for instructions.
- Publish flow renders included-skill selection and creates a template.
- Import flow renders skill forms.
- Import flow renders provider/model overrides.
- Successful import navigates to imported agent.

## Implementation Steps

1. Add marketplace models, repository, service, and router.
2. Add user publish support and optional seeded/curated template support.
3. Add template versioning and latest-version list behavior.
4. Add marketplace ranking by import count, then recency, then title.
5. Add `SkillService.validate_install_config(...)`.
6. Add provider/model validation reuse for imports.
7. Add list/detail/import-plan/import/publish/archive endpoints.
8. Add API tests.
9. Add SPA marketplace service/types.
10. Add Agents page `Marketplace` button.
11. Add publish action/form from agent detail/settings.
12. Add marketplace list and detail/import pages with formatted read-only instructions.
13. Add frontend tests if test harness exists for routes/forms.
14. Run:

```bash
cd api
uv run pytest -v
cd ../spa
yarn build
```

## Resolved Decisions

1. Users can publish agents immediately in v1.
2. Imported agents can override provider/model while keeping the template architecture and instructions.
3. OAuth-based skills are installed disabled until the importing user connects/enables them through the existing skills UI.
4. Marketplace details show formatted read-only instructions with no copy affordance, not raw editable persona text.
5. Marketplace templates support versioning in v1.
6. Marketplace search ranks by import count first, then recency, then alphabetically.
