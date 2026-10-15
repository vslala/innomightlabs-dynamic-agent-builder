"""The blueprint spec, `innomight/v2`: the parts of a blueprint document. The document itself, whose resources are
read from the kinds, is `document.Blueprint`.

Every field carries its description here. That text is the documentation: it reaches the JSON
Schema, the generated reference and the Builder's catalog. Skill config is not defined here; it is
generated from each skill's manifest (see `skills_schema.py`). See docs/LLD-solution-blueprints.md.
"""

import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.blueprints.diff import Each, Scalar
from src.blueprints.params import PARAM_TYPES
from src.connectors.mcp.providers import PROVIDERS
from src.form_models import FormInput
from src.knowledge.models import MAX_CRAWL_DEPTH, MAX_CRAWL_PAGES
from src.leads.models import visitor_input
from src.skills.models import ActorKind

API_VERSION = "innomight/v2"

ResourceName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]

#: The MCP servers InnomightLabs has presets for, read from the preset catalog rather than listed again.
McpProvider = Literal[tuple(PROVIDERS)]  # type: ignore[valid-type]

#: Audiences a skill can be shared with, read from ActorKind rather than listed again.
SharedAudience = Literal[tuple(kind.value for kind in ActorKind if kind is not ActorKind.OWNER)]  # type: ignore[valid-type]

AVAILABLE_TO_DESCRIPTION = (
    "Who besides you may use the skill. `visitor` is a signed-in widget user, "
    "`guest` is a widget user who gave only an email."
)

#: Marks a field whose value names other resources in the blueprint, and the kind they must be.
REF_KIND = "x-ref-kind"


def origin_of(url: str) -> str | None:
    """`https://example.com/about` → `https://example.com`; None for anything that isn't a web address."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc.lower()}"


def origins_of(urls: list[str]) -> list[str]:
    return sorted({origin for origin in map(origin_of, urls) if origin})


def _switch(value: Any, spec: Any) -> str:
    return f"switch to {spec.provider}" + (f" · {spec.model}" if spec.model else "")


def _allowed_on(value: Any, spec: Any) -> str:
    return "allow it on " + ", ".join(origins_of(spec.allowed_origins))


def _guests(value: Any, spec: Any) -> str:
    return "let guests chat with just an email" if value else "ask visitors to sign in"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParamSpec(Strict):
    """A value the person running the blueprint fills in."""

    type: Literal[tuple(PARAM_TYPES)] = Field(  # type: ignore[valid-type]
        "string",
        description="The kind of value expected. `text` is multi-line. `url` must start with http:// or https://.",
    )
    label: str = Field(description="Shown above the input when someone runs the blueprint.")
    description: str | None = Field(None, description="Help text under the input: what to enter and why it's needed.")
    default: str | int | bool | None = Field(
        None, description="Used when the person leaves the input empty. A param without a default is required."
    )
    options: list[str] = Field(
        default_factory=list, description="The allowed values. Required for `choice`, not allowed otherwise."
    )


#: The `description` field's documentation, shared by the kinds that store it.
DESCRIPTION = "What this resource is for. Stored as the resource's description where it has one."


class ResourceBase(Strict):
    id: str | None = Field(
        None,
        description="An existing resource to update instead of creating a new one. Without it, a resource with the "
        "same name is updated if there is one, and otherwise a new one is created.",
    )
    description: str | None = Field(None, description=DESCRIPTION)


class CrawlSpec(Strict):
    """Fill a knowledge base by reading a website."""

    url: str = Field(description="Where to start reading: a homepage for `mode: site`, a sitemap.xml for `mode: sitemap`.")
    mode: Literal["site", "sitemap"] = Field(
        "site",
        description="`site` follows links from `url` on the same domain. `sitemap` reads the pages listed in a sitemap.",
    )
    max_pages: int = Field(
        25,
        ge=1,
        le=MAX_CRAWL_PAGES,
        description="The most pages to read. Counts against your plan's knowledge base page allowance.",
    )
    max_depth: int = Field(3, ge=1, le=MAX_CRAWL_DEPTH, description="How many links away from `url` to follow.")


class KnowledgeBaseSpec(ResourceBase):
    """A searchable store of content an agent can answer from."""

    description: Annotated[str | None, Scalar(record="description", omit_none=True, says="update its description")] = (
        Field(None, description=DESCRIPTION)
    )
    kind: Literal["KnowledgeBase"] = Field(description="Which kind of resource to create.")
    name: Annotated[str, Scalar(record="name", says="rename to '{value}'")] = Field(
        min_length=1, description="Name shown in the dashboard's knowledge base list."
    )
    crawl: Annotated[
        CrawlSpec | None, Scalar(omit_none=True, says="read {crawl.url} again, up to {crawl.max_pages} pages")
    ] = Field(
        None, description="Fill the knowledge base by reading a website. Leave it out to create an empty knowledge base."
    )


class SkillEntry(Strict):
    """A skill to install on an agent. This shape parses any skill; the published schema and the validator
    replace it with one variant per skill manifest, carrying that skill's real config fields."""

    id: str = Field(description="Which skill to install.")
    config: dict[str, object] = Field(default_factory=dict, description="The skill's install settings.")
    available_to: list[SharedAudience] = Field(  # type: ignore[valid-type]
        default_factory=list, description=AVAILABLE_TO_DESCRIPTION
    )
    enabled: bool = Field(True, description="Install the skill switched off when false.")


class AgentSpec(ResourceBase):
    """An AI agent people can chat with in the dashboard, a widget or the API."""

    description: Annotated[
        str | None, Scalar(record="agent_description", omit_none=True, says="update its description")
    ] = Field(None, description=DESCRIPTION)
    kind: Literal["Agent"] = Field(description="Which kind of resource to create.")
    name: Annotated[str, Scalar(record="agent_name", says="rename to '{value}'")] = Field(
        min_length=1,
        description="The agent's name. Shown in the dashboard and as the widget title. "
        "Must not match one of your existing agents.",
    )
    instructions: Annotated[
        str, Scalar(record="agent_persona", normalise=str.strip, says="update its instructions")
    ] = Field(
        min_length=1, description="Who the agent is and how it should behave. This is the agent's system persona."
    )
    provider: Annotated[str, Scalar(record="agent_provider", says=_switch, group="model")] = Field(
        description="The LLM provider the agent uses, such as Bedrock, OpenAI (ChatGPT sign-in), OpenAIAPI "
        "(OpenAI API key), Anthropic or Gemini. "
        "It must be set up in Settings > Provider Configuration."
    )
    model: Annotated[str | None, Scalar(record="agent_model", omit_none=True, says=_switch, group="model")] = Field(
        None, description="Model id from that provider. Leave it out to use the provider's default model."
    )
    knowledge_bases: Annotated[
        list[ResourceName],
        Each(
            adds="link knowledge base '{name}'",
            removes="disconnect knowledge base '{title}'",
        ),
    ] = Field(
        default_factory=list,
        description="Knowledge bases in this blueprint the agent can search when answering.",
        json_schema_extra={REF_KIND: "KnowledgeBase"},
    )
    skills: Annotated[
        list[SkillEntry],
        Each(
            adds="add skill {label}",
            changes="update skill {label}",
            removes="uninstall skill {label}",
        ),
    ] = Field(default_factory=list, description="Skills to install on the agent, such as `lead_capture`.")
    mcp_connections: Annotated[
        list[ResourceName],
        Each(adds="give it the {title} tools", removes="take the {title} tools away"),
    ] = Field(
        default_factory=list,
        description="MCP connections in this blueprint whose tools the agent can use, such as web search.",
        json_schema_extra={REF_KIND: "McpConnection"},
    )
    session_timeout_minutes: Annotated[
        int | None,
        Scalar(record="session_timeout_minutes", omit_none=True, says="start conversations fresh after {value} minutes"),
    ] = Field(
        None, ge=0, description="Minutes of silence after which a conversation starts fresh. 0 means never."
    )


class WidgetKeySpec(ResourceBase):
    """A public key that lets a website embed an agent's chat widget."""

    kind: Literal["WidgetKey"] = Field(description="Which kind of resource to create.")
    agent: ResourceName = Field(
        description="The agent in this blueprint that the widget talks to.",
        json_schema_extra={REF_KIND: "Agent"},
    )
    name: Annotated[str | None, Scalar(record="name", omit_none=True, says="rename to '{value}'")] = Field(
        None, description='Label for the key in the dashboard. Defaults to "<agent name> widget".'
    )
    allowed_origins: Annotated[
        list[str],
        Scalar(record="allowed_origins", normalise=origins_of, unordered=True, says=_allowed_on),
    ] = Field(
        min_length=1,
        description="Sites allowed to embed the widget. Each is reduced to its origin, such as https://example.com.",
    )
    allow_guests: Annotated[bool, Scalar(record="allow_guests", says=_guests)] = Field(
        False, description="Let visitors chat after giving only their email, without Google sign-in."
    )


def lead_form_slug(resource_name: str) -> str:
    """A lead form's slug is its resource name with hyphens: `demo_request` is `{{ lead_form:demo-request }}`."""
    return resource_name.replace("_", "-")


def lead_form_resource(slug: str) -> str:
    return slug.replace("-", "_")


def _as_stored(form_inputs: list[Any]) -> list[dict[str, Any]]:
    """Fields as a lead form stores them, defaults filled in, so leaving a default out of a blueprint isn't a change."""
    return [
        visitor_input(FormInput.model_validate(form_input)).model_dump(mode="json", exclude_none=True)
        for form_input in form_inputs
    ]


class LeadFormSpec(ResourceBase):
    """A lead form: what an agent should find out from the people it talks to, field by field. An agent collects it
    when its instructions name it with `{{ lead_form:<slug> }}`, where the slug is this resource's name with hyphens
    (`demo_request` is `{{ lead_form:demo-request }}`). Give that agent the `lead_capture` skill too."""

    kind: Literal["LeadForm"] = Field(description="Which kind of resource to create.")
    name: Annotated[str, Scalar(record="name", says="rename to '{value}'")] = Field(
        min_length=1, max_length=80, description="The form's name, shown in the dashboard and at the top of the form."
    )
    purpose: Annotated[str | None, Scalar(record="purpose", omit_none=True, says="change why it collects this")] = Field(
        None, max_length=500, description="Why you collect it, in a sentence. The agent reads it to explain itself."
    )
    form_inputs: Annotated[list[FormInput], Scalar(record="form_inputs", normalise=_as_stored, says="change its fields")] = (
        Field(
            min_length=1,
            max_length=30,
            description="The fields, in the platform's form schema: `input_type` (text, text_area, select, choice or "
            "file_upload), `name`, `label`. Fields are required unless `attr.optional` is \"true\". Use "
            "`validation.format` for email, phone, url, number or date; `options` or `values` for select and choice; "
            "a choice with one value and `attr.variant: checkbox` for consent; `attr.agent_hint` to guide the agent.",
        )
    )


#: Where an Automation spec holds smart values (`{{ steps.draft.output }}`, `{{ trigger.lead.answers.email }}`),
#: which the automation resolves each run, so the blueprint leaves them as written. Every path is under
#: `resources.<name>.`.
SMART_VALUE_PATH = re.compile(
    r"^resources\.[a-z][a-z0-9_]*\.(steps\[\d+\]\.(prompt|arguments\b.*)|trigger\.schedule\.input\b.*)$"
)

STEP_NAME = r"^[a-z][a-z0-9_]{0,62}$"


class ManualTriggerSpec(Strict):
    """Started by hand, or by a test run."""


class ScheduleTriggerSpec(Strict):
    """Started by the clock, once or repeatedly."""

    cron: str | None = Field(
        None, description="To repeat: a 5-field cron expression (minute hour day month weekday), such as `0 9 * * 1`."
    )
    run_at: str | None = Field(
        None, description="To run once: a date and time (ISO 8601) in `timezone`. Set this or `cron`, not both."
    )
    timezone: str = Field("UTC", description="The timezone `cron` and `run_at` are read in, such as Europe/London.")
    input: dict[str, str] = Field(
        default_factory=dict, description="Fixed values every run gets, read in steps as `{{ input.<key> }}`."
    )


class LeadCapturedTriggerSpec(Strict):
    """Started whenever one of the account's agents captures a lead. Steps read it as
    `{{ trigger.lead.answers.<field> }}`, `{{ trigger.lead.capture_id }}`, `{{ trigger.lead.form_slug }}`."""

    form: str | None = Field(
        None,
        description="Only leads from this form: the LeadForm resource's name in this blueprint, or the slug of one "
        "already in the account. Leave it out for any form.",
    )
    agent: str | None = Field(
        None,
        description="Only leads this agent captured: an Agent in this blueprint, or an existing agent's id. Leave it "
        "out for any agent.",
    )
    include_test_captures: bool = Field(
        False, description="Also run for the test leads you make by chatting with the agent in the dashboard."
    )


class TriggerSpec(Strict):
    """What starts the automation: exactly one of `manual`, `schedule` or `lead_captured`."""

    manual: ManualTriggerSpec | None = Field(None, description="Start it by hand: `manual: {}`.")
    schedule: ScheduleTriggerSpec | None = Field(None, description="Start it on a schedule.")
    lead_captured: LeadCapturedTriggerSpec | None = Field(None, description="Start it when a lead is captured.")

    @model_validator(mode="after")
    def _exactly_one(self) -> "TriggerSpec":
        chosen = [name for name in ("manual", "schedule", "lead_captured") if getattr(self, name) is not None]
        if len(chosen) != 1:
            raise ValueError("Give exactly one of `manual`, `schedule` or `lead_captured`")
        return self


class StepSpec(Strict):
    """One step: ask an agent (`agent` and `prompt`), or run a skill action (`skill`, `action`, `arguments`)."""

    name: str = Field(
        pattern=STEP_NAME,
        description="The step's name, used by later steps to read its result: `{{ steps.<name>.output }}`.",
    )
    agent: str | None = Field(
        None,
        description="Ask this agent: an Agent in this blueprint, or an existing agent's id.",
        json_schema_extra={REF_KIND: "Agent"},
    )
    prompt: str | None = Field(
        None, description="What to ask the agent. May use smart values such as `{{ trigger.lead.answers.email }}`."
    )
    skill: str | None = Field(None, description="Run an action of this skill, one listed in the automation's `skills`.")
    action: str | None = Field(None, description="The skill action to run.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="The action's arguments. Values may use smart values."
    )

    @model_validator(mode="after")
    def _agent_or_skill(self) -> "StepSpec":
        asks_agent = self.agent is not None or self.prompt is not None
        runs_skill = self.skill is not None or self.action is not None
        if asks_agent == runs_skill:
            raise ValueError("A step either asks an agent (`agent` and `prompt`) or runs a skill action (`skill` and `action`)")
        if asks_agent and (self.agent is None or self.prompt is None):
            raise ValueError("Asking an agent needs both `agent` and `prompt`")
        if runs_skill and (self.skill is None or self.action is None):
            raise ValueError("Running a skill action needs both `skill` and `action`")
        return self


def _trigger_as_written(value: Any) -> dict[str, Any]:
    """A trigger as the spec dumps it, reduced to what it asks for, so defaults left out aren't differences."""
    plain = value.model_dump() if isinstance(value, BaseModel) else dict(value)
    name = next(key for key in ("manual", "schedule", "lead_captured") if plain.get(key) is not None)
    chosen = {key: item for key, item in plain[name].items() if item not in (None, "", {}, False)}
    if name == "lead_captured" and "form" in chosen:
        chosen["form"] = chosen["form"].replace("-", "_")  # a slug and its resource name are the same form
    if name == "schedule":
        chosen.setdefault("timezone", "UTC")
    return {name: chosen}


def _steps_as_written(steps: list[Any]) -> list[dict[str, Any]]:
    plain = [step.model_dump(exclude_none=True) if isinstance(step, BaseModel) else dict(step) for step in steps]
    return [{key: value for key, value in step.items() if value not in ({}, None)} for step in plain]


class AutomationSpec(ResourceBase):
    """A workflow that starts on its own and runs its steps in order: ask an agent, run a skill action. Use it to act
    on what happens elsewhere, such as emailing sales or posting to a CRM each time a lead is captured. It belongs to
    you and runs as you."""

    kind: Literal["Automation"] = Field(description="Which kind of resource to create.")
    title: Annotated[str, Scalar(record="title", says="rename to '{value}'")] = Field(
        min_length=1, max_length=200, description="The automation's name in the dashboard."
    )
    description: Annotated[str | None, Scalar(record="description", omit_none=True, says="update its description")] = (
        Field(None, description=DESCRIPTION)
    )
    enabled: Annotated[bool, Scalar(says=lambda value, spec: "turn it on" if value else "turn it off")] = Field(
        False,
        description="Turn it on, so its trigger starts it. Off, it's saved as a draft you can test in the dashboard.",
    )
    trigger: Annotated[TriggerSpec, Scalar(normalise=_trigger_as_written, says="change what starts it")] = Field(
        description="What starts it."
    )
    skills: Annotated[
        list[SkillEntry],
        Each(
            adds="add skill {label}",
            changes="update skill {label}",
            removes="remove skill {label}",
        ),
    ] = Field(
        default_factory=list,
        description="Skills the steps use, such as `send_email` or `rest_template`, set up like an agent's.",
    )
    steps: Annotated[list[StepSpec], Scalar(normalise=_steps_as_written, says="change its steps")] = Field(
        min_length=1, description="What it does, in order. Each step may read earlier steps' results."
    )


class McpConnectionSpec(ResourceBase):
    """A connection to an MCP server, such as Tavily web search, whose tools agents can use. It belongs to the
    account, so one connection serves every agent linked to it."""

    kind: Literal["McpConnection"] = Field(description="Which kind of resource to create.")
    provider: McpProvider | None = Field(  # type: ignore[valid-type]
        None,
        description="Which ready-made MCP server to connect, such as `tavily`. If the account isn't connected to "
        "it yet, the person signs in when you plan. Needed unless `id` names an existing connection.",
    )
    name: str | None = Field(None, description="Label in the dashboard. Defaults to the provider's name.")


class OutputSpec(Strict):
    """A value shown after a successful apply."""

    value: str = Field(description="The value to show. Usually a {{ resources.<name>.<attribute> }} reference.")
    description: str | None = Field(None, description="What the value is and what to do with it.")


class Metadata(Strict):
    name: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,62}$")] = Field(
        description="Short id for the blueprint, lowercase with dashes, such as site-agent."
    )
    title: str = Field(description="One-line human name, shown in lists and the marketplace.")
    description: str | None = Field(None, description="What the solution does for the person who runs it, in plain words.")
