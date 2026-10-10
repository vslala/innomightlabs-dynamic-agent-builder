"""The blueprint spec, `innomight/v2`: the parts of a blueprint document. The document itself, whose resources are
read from the kinds, is `document.Blueprint`.

Every field carries its description here. That text is the documentation: it reaches the JSON
Schema, the generated reference and the Builder's catalog. Skill config is not defined here; it is
generated from each skill's manifest (see `skills_schema.py`). See docs/LLD-solution-blueprints.md.
"""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.blueprints.diff import Each, Scalar
from src.blueprints.params import PARAM_TYPES
from src.connectors.mcp.providers import PROVIDERS
from src.knowledge.models import MAX_CRAWL_DEPTH, MAX_CRAWL_PAGES
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
        description="The LLM provider the agent uses, such as Bedrock, OpenAI, Anthropic or Gemini. "
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
