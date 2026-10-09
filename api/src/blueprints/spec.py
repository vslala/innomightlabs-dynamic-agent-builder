"""The blueprint spec, `innomight/v1`: the parts of a blueprint document. The document itself, whose resources are
read from the kinds, is `document.Blueprint`.

Every field carries its description here. That text is the documentation: it reaches the JSON
Schema, the generated reference and the Builder's catalog. Skill config is not defined here; it is
generated from each skill's manifest (see `skills_schema.py`). See docs/LLD-solution-blueprints.md.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.blueprints.params import PARAM_TYPES
from src.connectors.mcp.providers import PROVIDERS
from src.knowledge.models import MAX_CRAWL_DEPTH, MAX_CRAWL_PAGES
from src.skills.models import ActorKind

API_VERSION = "innomight/v1"

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
#: Marks a reference field that names things to take away, so it may name a resource that is being removed.
REMOVES = "x-removes"


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


class ResourceBase(Strict):
    id: str | None = Field(
        None,
        description="An existing resource to update instead of creating a new one. Without it, a resource with the "
        "same name is updated if there is one, and otherwise a new one is created.",
    )
    description: str | None = Field(
        None, description="What this resource is for. Stored as the resource's description where it has one."
    )
    remove: bool = Field(
        False,
        description="Delete this existing resource from the account. Needs its `id`. It can't be undone: a "
        "knowledge base loses its content, an agent its conversations and keys, a widget key stops working on "
        "the site. Leaving a resource out of a blueprint never removes it.",
    )


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

    kind: Literal["KnowledgeBase"] = Field(description="Which kind of resource to create.")
    name: str = Field(min_length=1, description="Name shown in the dashboard's knowledge base list.")
    crawl: CrawlSpec | None = Field(
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

    kind: Literal["Agent"] = Field(description="Which kind of resource to create.")
    name: str = Field(
        min_length=1,
        description="The agent's name. Shown in the dashboard and as the widget title. "
        "Must not match one of your existing agents.",
    )
    instructions: str = Field(
        min_length=1, description="Who the agent is and how it should behave. This is the agent's system persona."
    )
    provider: str = Field(
        description="The LLM provider the agent uses, such as Bedrock, OpenAI, Anthropic or Gemini. "
        "It must be set up in Settings > Provider Configuration."
    )
    model: str | None = Field(
        None, description="Model id from that provider. Leave it out to use the provider's default model."
    )
    knowledge_bases: list[ResourceName] = Field(
        default_factory=list,
        description="Knowledge bases in this blueprint the agent can search when answering.",
        json_schema_extra={REF_KIND: "KnowledgeBase"},
    )
    skills: list[SkillEntry] = Field(
        default_factory=list, description="Skills to install on the agent, such as `lead_capture`."
    )
    remove_knowledge_bases: list[ResourceName] = Field(
        default_factory=list,
        description="Knowledge bases in this blueprint to disconnect from the agent. The knowledge bases "
        "themselves stay, with their content.",
        json_schema_extra={REF_KIND: "KnowledgeBase", REMOVES: True},
    )
    mcp_connections: list[ResourceName] = Field(
        default_factory=list,
        description="MCP connections in this blueprint whose tools the agent can use, such as web search.",
        json_schema_extra={REF_KIND: "McpConnection"},
    )
    remove_mcp_connections: list[ResourceName] = Field(
        default_factory=list,
        description="MCP connections in this blueprint to take away from the agent. The connection itself stays "
        "on the account.",
        json_schema_extra={REF_KIND: "McpConnection", REMOVES: True},
    )
    remove_skills: list[str] = Field(
        default_factory=list,
        description="Skill ids to uninstall from the agent, with their settings and secrets. To only switch a "
        "skill off, list it under `skills` with `enabled: false` instead.",
    )
    session_timeout_minutes: int | None = Field(
        None, ge=0, description="Minutes of silence after which a conversation starts fresh. 0 means never."
    )


class WidgetKeySpec(ResourceBase):
    """A public key that lets a website embed an agent's chat widget."""

    kind: Literal["WidgetKey"] = Field(description="Which kind of resource to create.")
    agent: ResourceName = Field(
        description="The agent in this blueprint that the widget talks to.",
        json_schema_extra={REF_KIND: "Agent"},
    )
    name: str | None = Field(None, description='Label for the key in the dashboard. Defaults to "<agent name> widget".')
    allowed_origins: list[str] = Field(
        min_length=1,
        description="Sites allowed to embed the widget. Each is reduced to its origin, such as https://example.com.",
    )
    allow_guests: bool = Field(
        False, description="Let visitors chat after giving only their email, without Google sign-in."
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
