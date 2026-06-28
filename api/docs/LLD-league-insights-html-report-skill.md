# Low Level Design: League Insights HTML Report Skill

Date: 2026-06-27  
Status: Draft  
Owner: InnomightLabs API

## Summary
Add a first-party `league_insights_report` skill that generates a polished HTML5/CSS-only League of Legends insights report and stores it as a durable user artifact. The report should open in the user's browser when clicked from an automation result, agent response, or the artifact library.

The skill will:
- Use a Riot developer API key captured as an encrypted skill secret during enablement.
- Fetch Riot account and one or more match payloads with `httpx.AsyncClient`.
- Invoke a configured `krishna-mini` agent with an in-memory message repository to generate the report HTML.
- Validate and sanitize the generated HTML before saving it to S3 through the artifact system.
- Return a compact result containing the artifact id, title, and browser-openable report URL.

## Current Architecture Fit
The platform already has most of the required foundations:

- Skill manifests support encrypted install-time fields through `attr.secret: "true"`.
- Automation skill config also splits secret fields and stores encrypted secrets.
- `FormOptionsSourceType.KRISHNA_MINI_AGENTS` already filters agent selectors to `agent_architecture == "krishna-mini"`.
- `get_agent_architecture(..., message_repository=get_message_repository("in_memory"))` lets a skill reuse an existing agent without persisting the temporary report-generation conversation.
- `ArtifactService.create_artifact(...)` already creates durable S3-backed artifact records owned by the user.

The main missing platform capability is an inline browser view URL for HTML artifacts. Current artifact URLs are generated with `Content-Disposition: attachment`, which makes HTML reports download instead of opening as a page.

## Naming
Use:

- Folder: `api/src/skills/league_insights_report/`
- Skill id: `league_insights_report`
- Namespace: `games.league_of_legends`
- Display name: `League Insights Report`
- Artifact type: existing `html_report`

## Files
Add:

- `api/src/skills/league_insights_report/__init__.py`
- `api/src/skills/league_insights_report/manifest.yml`
- `api/src/skills/league_insights_report/actions.py`
- `api/src/skills/league_insights_report/models.py`
- `api/src/skills/league_insights_report/riot_client.py`
- `api/src/skills/league_insights_report/report_agent.py`
- `api/src/skills/league_insights_report/report_data.py`
- `api/src/skills/league_insights_report/html_safety.py`
- `api/tests/test_league_insights_report_skill.py`

Update:

- `api/src/artifacts/storage.py`
- `api/src/artifacts/service.py`
- `api/src/artifacts/router.py`
- `api/src/artifacts/models.py`
- `api/tests/test_artifacts.py`

## Riot API Scope
Use Riot's official API surface for the first version:

- Account lookup by Riot ID through `account-v1`.
- Match id lookup by PUUID through `match-v5`.
- Match detail lookup through `match-v5`.

The action should ask for the user's Riot game name and tag line, then resolve the PUUID and fetch either:

- One or more explicit `match_ids`, if supplied.
- A single latest match when `report_scope=single_match` and no `match_ids` are supplied.
- A bounded set of recent matches when `report_scope=multi_match`.

Keep region handling explicit:

- `routing_region`: `americas`, `asia`, `europe`, or `sea`.
- `platform_region`: optional for future expansion, but not required for `match-v5`.

Bound multi-match reports in v1:

- Default `match_count`: `5`
- Maximum `match_count`: `10`
- Fetch match details sequentially or with a small concurrency limit of `3` to avoid avoidable Riot rate-limit pressure.

## Artifact Browser View
Current artifact responses expose a single `url` generated as an attachment. Add a separate browser-openable URL for HTML artifacts.

Recommended model change:

```python
class ArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    source: ArtifactSource
    created_at: datetime
    url: str | None = None
    view_url: str | None = None
```

Recommended storage change:

```python
def presign_get_url(
    self,
    key: str,
    filename: str | None = None,
    *,
    disposition: str = "attachment",
    content_type: str | None = None,
) -> str:
    params = {"Bucket": self.bucket, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = (
            f'{disposition}; filename="{sanitize_filename(filename)}"'
        )
    if content_type:
        params["ResponseContentType"] = content_type
    return str(self.client.generate_presigned_url(...))
```

Recommended service/router additions:

- `ArtifactService.view_url(owner_email, artifact_id) -> str`
- `GET /artifacts/{artifact_id}/view -> {"url": "..."}`

For `html_report`, generate the view URL with:

- `Content-Disposition: inline`
- `Content-Type: text/html; charset=utf-8`

For non-viewable artifacts, either return the download URL or reject with `400`. Prefer rejecting with `400` for v1 so the contract is explicit.

Future hardening: serve HTML through an authenticated API proxy with strict headers:

- `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:;`
- `X-Content-Type-Options: nosniff`

Presigned S3 inline URLs are enough for v1 if generated HTML is sanitized and contains no script or external resources.

Reports should be shareable later. Do not build public sharing in this skill implementation, but keep the artifact model independent enough to support a future artifact sharing layer with stable share ids, visibility controls, revocation, and public read routes. The report skill should only create owner-private artifacts for now.

## Manifest Design
`api/src/skills/league_insights_report/manifest.yml`:

```yaml
id: league_insights_report
namespace: games.league_of_legends
name: League Insights Report
description: Generate a browser-openable HTML League of Legends match or multi-match insights report.
repeatable: true
repeatable_identity_fields: [report_agent_id]
system_prompt: |
  Use this skill when the user asks for a League of Legends match analysis or recent-match trend report.
  The skill creates a durable HTML artifact and returns a link the user can open in their browser.
  Never expose the Riot API key. It is stored in encrypted skill configuration.
form:
  - input_type: select
    name: report_agent_id
    label: Report agent
    options_source:
      type: krishna_mini_agents
  - input_type: password
    name: riot_api_key
    label: Riot API key
    attr:
      secret: "true"
      placeholder: RGAPI-...
  - input_type: select
    name: default_routing_region
    label: Default routing region
    value: europe
    options:
      - label: Americas
        value: americas
      - label: Asia
        value: asia
      - label: Europe
        value: europe
      - label: SEA
        value: sea
actions:
  - name: generate_match_report
    aliases: [generate_lol_report, league_match_report]
    description: Fetch League match data from Riot and create a detailed HTML report artifact.
    input_schema:
      type: object
      required: [game_name, tag_line]
      properties:
        game_name:
          type: string
          description: Riot ID game name, for example ThePlayer.
        tag_line:
          type: string
          description: Riot ID tag line without #, for example EUW.
        report_scope:
          type: string
          enum: [single_match, multi_match]
          description: Whether to generate a single-match report or a multi-match trend report.
        match_id:
          type: string
          description: Optional Riot match id for a single-match report.
        match_ids:
          oneOf:
            - type: array
              items:
                type: string
            - type: string
          description: Optional Riot match ids for a multi-match report. Automation forms may pass a comma-separated string; agents may pass an array.
        match_count:
          type: integer
          description: Number of recent matches to analyze for multi-match reports, clamped to 1-10.
        routing_region:
          type: string
          enum: [americas, asia, europe, sea]
          description: Riot regional routing value. Defaults to skill configuration.
        queue:
          type: integer
          description: Optional Riot queue id filter for latest-match lookup.
        report_title:
          type: string
          description: Optional title for the generated artifact.
    action_form:
      form_name: League Insights Report
      submit_path: ""
      form_inputs:
        - input_type: text
          name: game_name
          label: Riot game name
          attr:
            placeholder: ThePlayer
            smart_values: "true"
        - input_type: text
          name: tag_line
          label: Riot tag line
          attr:
            placeholder: EUW
            smart_values: "true"
        - input_type: text
          name: match_id
          label: Match id
          attr:
            optional: "true"
            smart_values: "true"
        - input_type: text
          name: match_ids
          label: Match ids
          attr:
            optional: "true"
            smart_values: "true"
            placeholder: "EUW1_123, EUW1_456"
        - input_type: select
          name: report_scope
          label: Report scope
          value: single_match
          options:
            - label: Single match
              value: single_match
            - label: Multi-match trend
              value: multi_match
        - input_type: number
          name: match_count
          label: Recent match count
          value: "5"
          attr:
            optional: "true"
            min: "1"
            max: "10"
        - input_type: select
          name: routing_region
          label: Routing region
          options:
            - label: Use skill default
              value: ""
            - label: Americas
              value: americas
            - label: Asia
              value: asia
            - label: Europe
              value: europe
            - label: SEA
              value: sea
        - input_type: text
          name: report_title
          label: Report title
          attr:
            optional: "true"
            smart_values: "true"
    handler: actions:generate_match_report
```

## Request Models
`api/src/skills/league_insights_report/models.py` should validate the action input and skill config.

```python
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

ROUTING_REGIONS = {"americas", "asia", "europe", "sea"}
REPORT_SCOPES = {"single_match", "multi_match"}
DEFAULT_MATCH_COUNT = 5
MAX_MATCH_COUNT = 10


class LeagueReportConfig(BaseModel):
    report_agent_id: str
    riot_api_key: str
    default_routing_region: str = "europe"

    @model_validator(mode="after")
    def normalize(self) -> "LeagueReportConfig":
        self.report_agent_id = self.report_agent_id.strip()
        self.riot_api_key = self.riot_api_key.strip()
        self.default_routing_region = self.default_routing_region.strip().lower()
        if not self.report_agent_id:
            raise ValueError("report_agent_id is required")
        if not self.riot_api_key:
            raise ValueError("riot_api_key is required")
        if self.default_routing_region not in ROUTING_REGIONS:
            raise ValueError("default_routing_region must be americas, asia, europe, or sea")
        return self


class GenerateMatchReportRequest(BaseModel):
    game_name: str
    tag_line: str
    report_scope: str = "single_match"
    match_id: str | None = None
    match_ids: list[str] | str = Field(default_factory=list)
    match_count: int = DEFAULT_MATCH_COUNT
    routing_region: str | None = None
    queue: int | None = None
    report_title: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "GenerateMatchReportRequest":
        self.game_name = self.game_name.strip()
        self.tag_line = self.tag_line.strip().lstrip("#")
        self.report_scope = self.report_scope.strip().lower()
        self.match_id = self.match_id.strip() if self.match_id else None
        raw_match_ids = self.match_ids.split(",") if isinstance(self.match_ids, str) else self.match_ids
        self.match_ids = [item.strip() for item in raw_match_ids if item.strip()]
        self.routing_region = self.routing_region.strip().lower() if self.routing_region else None
        self.report_title = self.report_title.strip() if self.report_title else None
        self.match_count = max(1, min(MAX_MATCH_COUNT, int(self.match_count)))
        if not self.game_name:
            raise ValueError("game_name is required")
        if not self.tag_line:
            raise ValueError("tag_line is required")
        if self.report_scope not in REPORT_SCOPES:
            raise ValueError("report_scope must be single_match or multi_match")
        if self.match_id and self.match_ids:
            raise ValueError("Provide either match_id or match_ids, not both")
        if self.report_scope == "single_match" and len(self.match_ids) > 1:
            raise ValueError("single_match report accepts at most one match id")
        if self.routing_region and self.routing_region not in ROUTING_REGIONS:
            raise ValueError("routing_region must be americas, asia, europe, or sea")
        return self
```

## Riot Client
Keep Riot I/O isolated in `riot_client.py`.

Responsibilities:

- Build regional API base URLs.
- Add `X-Riot-Token` without logging it.
- Translate Riot HTTP errors into user-readable messages.
- Return bounded, normalized dicts that are safe to pass to the report agent.

Recommended shape:

```python
class RiotClient:
    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.http_client = http_client

    async def get_account_by_riot_id(
        self,
        *,
        routing_region: str,
        game_name: str,
        tag_line: str,
    ) -> RiotAccount:
        ...

    async def get_match_ids(
        self,
        *,
        routing_region: str,
        puuid: str,
        queue: int | None = None,
        count: int,
    ) -> list[str]:
        ...

    async def get_match(
        self,
        *,
        routing_region: str,
        match_id: str,
    ) -> dict[str, Any]:
        ...
```

Do not retry `401`, `403`, or `404`. A single retry is acceptable for `429` and `5xx` later, but v1 can surface a clear error and rely on automation retry behavior.

## Report Data Normalization
Keep raw Riot payload pruning in `report_data.py`.

Responsibilities:

- Select the target participant by PUUID for every match.
- Keep only fields needed by the report prompt.
- Derive simple metrics before calling the agent, such as KDA, kill participation, damage share, gold share, vision score, objective participation, win/loss, champion, lane/team position, queue id, duration, and team objective totals.
- Build different prompt payloads for `single_match` and `multi_match`.
- Bound serialized report data before agent invocation.

For `multi_match`, include aggregate trend fields:

- `matches_analyzed`
- `wins`, `losses`, `win_rate`
- champion distribution
- average KDA and deaths
- average damage, gold, CS, vision score
- recurring strengths and weaknesses based on derived stats
- per-match summary rows

Do not ask the agent to infer basic arithmetic from raw match JSON when the backend can compute it deterministically.

## Report Agent Invocation
`report_agent.py` should encapsulate Krishna-mini usage.

The important behavior is:

- Look up `report_agent_id` under the skill owner.
- Reject the selected agent if `agent.agent_architecture != "krishna-mini"`.
- Create a temporary `Conversation` object without saving it.
- Use `get_agent_architecture("krishna-mini", message_repository=get_message_repository("in_memory"))`.
- Call `handle_message_buffered(...)`.
- Return only `response_text`.

Recommended helper:

```python
async def generate_report_html_with_agent(
    *,
    agent_id: str,
    owner_email: str,
    actor_email: str,
    actor_id: str,
    prompt: str,
) -> str:
    agent = AgentRepository().find_agent_by_id(agent_id, owner_email)
    if not agent:
        raise ValueError("Report agent not found")
    if agent.agent_architecture != "krishna-mini":
        raise ValueError("Report agent must use krishna-mini architecture")

    conversation = Conversation(
        agent_id=agent.agent_id,
        created_by=owner_email,
        title="Temporary report generation",
        description="In-memory report generation session",
    )
    architecture = get_agent_architecture(
        agent.agent_architecture,
        message_repository=get_message_repository("in_memory"),
    )
    result = await architecture.handle_message_buffered(...)
    if not result.success:
        raise ValueError(result.error or "Report generation failed")
    return result.response_text
```

Because Krishna-mini has a concise default system directive, the report prompt must explicitly ask for a complete HTML document. The explicit task prompt should win because the user message is concrete and specific.

## Report Prompt
Build the prompt from normalized match data, not raw unbounded Riot payloads.

Prompt requirements:

- Output exactly one complete HTML5 document.
- Use inline CSS inside a single `<style>` tag.
- Do not use JavaScript.
- Do not use external images, fonts, stylesheets, scripts, iframes, or network resources.
- For single-match reports, include sections for overview, player performance, lane/macro insights, combat highlights, objective control, mistakes, recommendations, and next-game checklist.
- For multi-match reports, include sections for trend overview, champion/role patterns, consistency, recurring strengths, recurring mistakes, objective trends, improvement priorities, and practice checklist.
- Use semantic HTML and accessible contrast.
- Keep the report self-contained and browser-openable.

`report_agent.py` should strip markdown fences before validation, because models often wrap HTML in ```html.

## HTML Safety
Generated HTML will be opened in the user's browser, so validate it before storing.

V1 should avoid new dependencies and implement a small standard-library validator in `html_safety.py` using `html.parser.HTMLParser`.

Reject HTML that contains:

- `<script>`
- `<iframe>`
- `<object>`
- `<embed>`
- `<base>`
- `<form>`
- `<input>`
- `<button>`
- `<link>`
- `<meta http-equiv=refresh>`
- Any attribute starting with `on`
- Any `href` or `src` value with `javascript:`, `data:text/html`, or external `http(s)` URLs
- CSS `@import`
- CSS `url(http...)` or `url(javascript:...)`

Allow:

- A single full HTML document.
- Inline `<style>`.
- Data images only if we intentionally add chart images later. For v1, prefer no images.

Recommended functions:

```python
def extract_html_document(text: str) -> str:
    ...

def validate_safe_report_html(html: str) -> None:
    ...
```

If validation fails, raise a clear error and do not create an artifact.

## Action Flow
`actions.generate_match_report(...)`:

1. Validate config with `LeagueReportConfig`.
2. Validate arguments with `GenerateMatchReportRequest`.
3. Resolve `routing_region = request.routing_region or config.default_routing_region`.
4. Fetch Riot account by Riot ID.
5. Resolve target match ids:
   - Use `match_ids` when supplied.
   - Use `[match_id]` when supplied.
   - Use `match_count=1` for `single_match` latest-match lookup.
   - Use bounded `match_count` for `multi_match` latest-match lookup.
6. Fetch all target match details with bounded concurrency.
7. Normalize match details into a compact report data object.
8. Build the report prompt.
9. Invoke the configured Krishna-mini report agent in memory.
10. Extract and validate the returned HTML.
11. Save artifact through `ArtifactService.create_artifact(...)`.
12. Return compact automation-friendly output.

Return shape:

```python
{
    "ok": true,
    "artifact_id": "artifact-uuid",
    "title": "League Match Report - ThePlayer#EUW",
    "filename": "league-match-report-ThePlayer-EUW.html",
    "url": "https://...",
    "view_url": "https://...",
    "report_scope": "single_match",
    "match_ids": ["EUW1_1234567890"],
    "routing_region": "europe"
}
```

On expected Riot failures, return `ok: false` when the automation can branch usefully:

```python
{
    "ok": false,
    "status_code": 403,
    "error": "Riot API rejected the configured API key. Check that the key is valid and not expired."
}
```

On invalid configuration or unsafe generated HTML, raise `ValueError` because those are platform/configuration errors, not ordinary game-data results.

## Artifact Source Metadata
When saving the report:

```python
ArtifactSource(
    skill_id="league_insights_report",
    agent_id=config.report_agent_id,
    automation_id=context.get("automation_id"),
    automation_run_id=context.get("automation_run_id"),
    automation_node_id=context.get("automation_node_id"),
    conversation_id=context.get("conversation_id"),
    metadata={
        "game": "league_of_legends",
        "routing_region": routing_region,
        "report_scope": request.report_scope,
        "match_ids": match_ids,
        "riot_id": f"{request.game_name}#{request.tag_line}",
    },
)
```

This keeps report ownership tied to the user artifact system, not the skill installation. If the skill is later uninstalled, the generated report remains available in the user's artifacts.

## Automation Behavior
The action form uses smart values for user-facing fields. The Riot key stays in encrypted skill config and is not part of automation node output or prompt text.

Example automation result fields:

```json
{
  "ok": true,
  "artifact_id": "9f3c...",
  "view_url": "https://...",
  "report_scope": "multi_match",
  "match_ids": ["EUW1_...", "EUW1_..."]
}
```

Downstream branches can check:

- `{{ nodes.generate_report.result.ok }}`
- `{{ nodes.generate_report.result.artifact_id }}`
- `{{ nodes.generate_report.result.view_url }}`
- `{{ nodes.generate_report.result.report_scope }}`

## Agent Behavior
When installed on an agent, the agent can call `generate_match_report` after asking for:

- Riot game name
- Riot tag line
- Optional region, report scope, match id, match ids, or recent match count

The skill result should be compact, so the agent can simply tell the user that the report is ready and provide the `view_url`.

## Tests
Add `api/tests/test_league_insights_report_skill.py`.

Coverage:

- Manifest install form marks `riot_api_key` as secret.
- Install form uses `krishna_mini_agents` for `report_agent_id`.
- Config validation rejects missing Riot key.
- Action rejects a non-krishna-mini report agent.
- Riot client sends `X-Riot-Token` and does not expose the token in errors.
- Riot 401/403 returns `ok:false` with a human-readable error.
- Single latest-match flow calls account lookup, match id lookup with count 1, and match detail lookup.
- Multi-match latest flow calls account lookup, match id lookup with bounded count, and multiple match detail lookups.
- Explicit `match_id` flow skips match id lookup.
- Explicit `match_ids` array flow skips match id lookup and fetches each requested match.
- Explicit comma-separated `match_ids` string from automation forms is normalized to a list.
- `match_count` is clamped to the configured maximum.
- Report data normalization computes deterministic single-match and multi-match metrics before agent invocation.
- Agent invocation uses in-memory message repository.
- Markdown-fenced HTML is extracted correctly.
- Unsafe HTML with script/event handlers/external resources is rejected.
- Safe HTML is saved as an `html_report` artifact.
- Result includes `artifact_id`, `url`, and `view_url`.
- Artifact `view_url` uses inline content disposition and HTML content type.
- Existing artifact download behavior remains attachment-based.

Run:

```bash
cd api
uv run pytest -v
```

## Implementation Steps
1. Extend artifacts with `view_url` support for `html_report` without changing existing download behavior.
2. Add tests for inline artifact URL generation.
3. Add `league_insights_report` skill manifest and models with single-match and multi-match controls.
4. Add Riot client with bounded error translation.
5. Add report-data normalization for single-match and multi-match payloads.
6. Add report-agent helper using Krishna-mini plus in-memory message repository.
7. Add HTML extraction and safety validation.
8. Add action orchestration and artifact creation.
9. Add unit tests with mocked Riot responses, mocked agent HTML, and mocked artifact storage.
10. Run the full API test suite.

## Deferred Work
- Public artifact sharing should be designed as a separate artifact-platform feature with stable share ids, visibility controls, revocation, analytics, and public routes.
- Marketplace automation templates should be designed separately as a flexible template system. The League report automation can become one template after the skill lands, but the skill itself should stay simple and reusable.
