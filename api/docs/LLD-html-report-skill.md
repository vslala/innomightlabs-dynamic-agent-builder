# Low Level Design: HTML Report Skill

Date: 2026-06-27  
Status: Draft  
Owner: InnomightLabs API

## Summary
Add a first-party `html_report` skill that generates detailed, styled HTML5 reports with CSS only, persists them as user-owned artifacts, and returns a browser-openable report URL.

The skill is intended for automations and agents. Example use cases:
- League of Legends match insight reports
- SEO audit reports
- customer health summaries
- sales call summaries
- weekly operations reports

The skill should use a configured `krishna-mini` agent with an in-memory conversation history so report generation does not write conversation messages to DynamoDB. Each invocation is a fresh temporary session but reuses the selected agent's persona, provider, model, and provider credentials.

## Product Boundary
Keep this skill generic.

`html_report` should not fetch League of Legends data and should not own the Riot API key. It should receive prepared data and instructions, then create the report. Riot API access belongs in one of these upstream options:
- `rest_template` automation step using `{{ riot_api_key }}` environment placeholder in the `X-Riot-Token` header.
- a future `league_insights` skill with Riot-specific fetch/normalize actions.
- a vertical League automation template that wires data fetch -> analysis -> HTML report.

This keeps the report skill reusable across all domains.

## Existing System Fit
Relevant existing pieces:
- Generic user artifacts exist under `api/src/artifacts`.
- Artifact files are stored in the private `conversation_media_bucket`.
- Artifact metadata is owner-scoped in DynamoDB with `pk=User#{owner_email}`.
- `ArtifactService.create_artifact(...)` uploads bytes and returns signed artifact metadata.
- `get_agent_architecture(...)` accepts a `message_repository` override.
- `InMemoryMessageRepository` already exists.
- `form_options.py` has `krishna_mini_agents`, which returns only agents where `agent_architecture == "krishna-mini"`.

## Riot API Notes for League Templates
For League workflows, use Riot ID -> PUUID -> match history:
- Riot recommends Riot IDs and PUUID-based flows instead of summoner names.
- `ACCOUNT-V1 /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}` obtains PUUID from Riot ID.
- `MATCH-V5` can then fetch match IDs and match details by PUUID.
- Riot monetization requires product registration, approved/acknowledged status, a free tier, and transformative paid content.
- Riot policy prohibits betting/gambling, unfair advantage, game-session-specific hidden information, alternative MMR/ELO calculators, and apps that dictate player decisions.

Therefore the first League template should be post-game coaching and reporting, not live-game advantage.

Source: Riot Developer Portal, League docs and policy.

## Skill Files
Add:
- `api/src/skills/html_report/__init__.py`
- `api/src/skills/html_report/manifest.yml`
- `api/src/skills/html_report/actions.py`
- `api/src/skills/html_report/models.py`
- `api/src/skills/html_report/report_runtime.py`
- `api/src/skills/html_report/html_safety.py`
- `api/tests/test_html_report_skill_actions.py`

Optional later:
- `api/src/skills/league_insights/...` for Riot-specific data fetch and match normalization.

## Manifest
`api/src/skills/html_report/manifest.yml`:

```yaml
id: html_report
namespace: core.reporting
name: HTML Report
description: Generate a styled HTML5 report and save it as a user artifact.
repeatable: true
repeatable_identity_fields: [target_agent_id]
system_prompt: |
  Use this skill to generate polished HTML reports from structured data or report instructions.
  The report is saved as an artifact and returned as a browser-openable URL.
  The selected report agent must be a krishna-mini agent.
form:
  - input_type: select
    name: target_agent_id
    label: Report agent
    options_source:
      type: krishna_mini_agents
  - input_type: text_area
    name: usage_description
    label: When should this report generator be used?
    attr:
      rows: "4"
      placeholder: "Use this for League of Legends match reports, weekly summaries, and stakeholder-ready dashboards."
      expose_to_runtime: "true"
      usage_context_label: "Use when"
      usage_context_max_chars: "500"
actions:
  - name: generate
    aliases: [create_report, generate_report, html_report]
    description: Generate an HTML5 report from instructions and data, save it as an artifact, and return the artifact URL.
    input_schema:
      type: object
      required: [title, report_prompt]
      properties:
        title:
          type: string
          description: Human-readable report title.
        report_prompt:
          type: string
          description: Instructions for what the report should explain, emphasize, and conclude.
        data:
          description: Structured report data. May be an object, list, or string.
        filename:
          type: string
          description: Optional output filename. Defaults from title.
        theme:
          type: string
          enum: [default, esports, executive, technical]
          description: Optional visual style preset.
    action_form:
      form_name: Generate HTML Report
      submit_path: ""
      form_inputs:
        - input_type: text
          name: title
          label: Title
          attr:
            smart_values: "true"
        - input_type: text_area
          name: report_prompt
          label: Report instructions
          attr:
            rows: "8"
            smart_values: "true"
        - input_type: text_area
          name: data
          label: Report data
          attr:
            rows: "12"
            smart_values: "true"
            optional: "true"
            placeholder: "{{ $.nodes.fetch_match.output.result.body_preview }}"
        - input_type: text
          name: filename
          label: Filename
          attr:
            smart_values: "true"
            optional: "true"
            placeholder: "league-match-report.html"
        - input_type: select
          name: theme
          label: Theme
          value: default
          values: [default, esports, executive, technical]
    handler: actions:generate
```

## Action Model
`api/src/skills/html_report/models.py`:

```python
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class GenerateReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    report_prompt: str = Field(min_length=1, max_length=12000)
    data: Any | None = None
    filename: str | None = Field(default=None, max_length=180)
    theme: Literal["default", "esports", "executive", "technical"] = "default"

    @model_validator(mode="after")
    def normalize(self) -> "GenerateReportRequest":
        self.title = self.title.strip()
        self.report_prompt = self.report_prompt.strip()
        if isinstance(self.data, str):
            value = self.data.strip()
            if value:
                try:
                    self.data = json.loads(value)
                except json.JSONDecodeError:
                    self.data = value
            else:
                self.data = None
        if self.filename:
            self.filename = self.filename.strip()
        return self
```

## Runtime Flow
`actions.generate(...)` should:
1. Validate action arguments.
2. Resolve `owner_email`, `actor_email`, and orchestration metadata from runtime context.
3. Resolve the target report agent:
   - Prefer installed skill config `target_agent_id`.
   - Optionally allow action argument override later, but only if the selected agent is `krishna-mini`.
4. Build a temporary `Conversation` object with a generated id. Do not save it.
5. Create `InMemoryMessageRepository`.
6. Create architecture with `get_agent_architecture(agent.agent_architecture, message_repository=in_memory_repo)`.
7. Invoke `handle_message_buffered(...)` with a strict report-generation prompt.
8. Extract HTML from `response_text`.
9. Validate/sanitize HTML.
10. Store report with `ArtifactService.create_artifact(...)`.
11. Return artifact metadata and URL.

## Report Prompt Contract
The report-generation prompt must override Krishna-mini's default "concise" style for this task.

Prompt skeleton:

```text
You are generating a complete HTML report artifact.

Return ONLY a complete HTML5 document.
Do not wrap it in Markdown.
Do not include explanations outside the HTML.

Hard constraints:
- Use HTML5 and CSS only.
- No JavaScript.
- No external scripts.
- No external stylesheets.
- No iframes.
- Inline CSS inside a <style> tag is allowed.
- The report must be visually polished and readable in a browser.
- Use semantic sections, tables, summary cards, and clear headings where appropriate.
- Include the supplied title.

Theme: {theme}
Title: {title}

Report instructions:
{report_prompt}

Data:
{json_or_text_data}
```

## HTML Safety
`html_safety.py` should enforce a bounded safety policy before upload.

V1 checks:
- Must contain `<!doctype html` or `<html`.
- Reject `<script`.
- Reject `<iframe`.
- Reject inline event handlers such as `onclick=`, `onload=`, `onerror=`.
- Reject `javascript:` URLs.
- Reject remote stylesheet/script imports.
- Enforce max HTML bytes, e.g. 1 MB.

This is not a full sanitizer, but it is a strong first boundary. Later we can add an allowlist sanitizer such as `bleach` if dependency policy allows.

## Artifact Storage
Use the artifact system:

```python
ArtifactService().create_artifact(
    owner_email=owner_email,
    artifact_type="html_report",
    title=request.title,
    filename=filename,
    mime_type="text/html",
    body=html.encode("utf-8"),
    source=ArtifactSource(
        skill_id="html_report",
        agent_id=agent.agent_id,
        automation_id=context.get("automation_id"),
        automation_run_id=context.get("automation_run_id"),
        automation_node_id=context.get("automation_node_id"),
        conversation_id=context.get("conversation_id"),
        metadata={"theme": request.theme},
    ),
)
```

The returned artifact URL should open in the user's browser. For V1 it can be a presigned S3 URL returned by `ArtifactService`. Later, the dashboard can route to `/dashboard/artifacts/{artifact_id}` and render a preview panel.

## Automation Behavior
An automation can wire:

```text
REST Template: fetch Riot match data
-> optional analysis/summarization step
-> HTML Report: generate
-> Send Email or notification with artifact URL
```

For Riot:

```json
{
  "url": "https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{{ $.input.puuid }}/ids",
  "headers": {
    "X-Riot-Token": "{{ riot_api_key }}"
  }
}
```

`{{ $.input.puuid }}` is rendered by automation smart values. `{{ riot_api_key }}` is resolved by `rest_template` from environment variables.

## Agent Behavior
When used by an agent:
- The agent calls `html_report.generate` with title, instructions, and data.
- The report skill invokes the configured Krishna-mini report agent internally.
- The result should include:

```json
{
  "type": "html_report",
  "artifact_id": "...",
  "title": "...",
  "filename": "...",
  "url": "https://...",
  "size_bytes": 12345
}
```

## Krishna-mini Reliability Review
Current `krishna-mini` is suitable for report generation because:
- It does not use tools.
- It saves messages through an injectable repository.
- It can use `InMemoryMessageRepository`.
- It performs a single provider call, which is easier to reason about than a tool loop.

Caveat:
- Its built-in system prompt asks for concise conversational responses. The report skill must provide a strong user prompt requiring a complete HTML document. If this is unreliable in testing, add a dedicated `handle_report_generation(...)` helper or a `mode` parameter for Krishna-mini that uses a report-specific system prompt.

## API Key Handling
Riot keys should not be stored on `html_report`.

Options for League workflows:
- Environment placeholder: `{{ riot_api_key }}` used in `rest_template` headers.
- Future League skill install form with `password` field `riot_api_key` marked `secret: "true"`.
- Future organization-level secret manager for reusable automation secrets.

For the first implementation, use environment placeholders or a future Riot-specific skill. Keep `html_report` clean and provider-agnostic.

## Tests
Add `api/tests/test_html_report_skill_actions.py`:
- install schema uses `krishna_mini_agents`.
- `generate` rejects missing runtime `owner_email`.
- selected target agent must exist and be owned by user.
- selected target agent must be `krishna-mini`.
- uses `InMemoryMessageRepository` when invoking architecture.
- does not save a real conversation.
- strips/extracts HTML from model response.
- rejects script/iframe/event-handler HTML.
- creates `html_report` artifact with `text/html`.
- returns artifact id and URL.

Add focused tests for `html_safety.py`:
- accepts complete HTML5 document.
- rejects scripts.
- rejects inline event handlers.
- rejects `javascript:` URLs.
- rejects oversized HTML.

## Implementation Steps
1. Add `html_report` skill folder, manifest, models, safety helpers, and runtime helper.
2. Implement `generate` action using `krishna-mini` + `InMemoryMessageRepository`.
3. Store output through `ArtifactService`.
4. Add tests with fake agent repository, fake architecture result, and fake artifact service.
5. Run:

```bash
cd api
uv run pytest -v
```

## Follow-Up: League Vertical Template
After `html_report` exists, build a League template:
1. Input form: Riot ID, tagline, platform, region, match count.
2. REST step: Riot ID -> PUUID.
3. REST step: PUUID -> match ids.
4. REST step(s): match id -> match details.
5. HTML report step: generate report.
6. Optional schedule: weekly ranked progress report.
7. Optional artifact email/share step.
