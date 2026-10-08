"""The blueprint spec, `innomight/v1`: the structure of a blueprint document.

Every field carries its description here. That text is the documentation: it reaches the JSON
Schema, the generated reference and the Builder's catalog. Skill config is not defined here; it is
generated from each skill's manifest (see `skills_schema.py`). See docs/LLD-solution-blueprints.md.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.knowledge.models import MAX_CRAWL_DEPTH, MAX_CRAWL_PAGES
from src.skills.models import ActorKind

API_VERSION = "innomight/v1"

ResourceName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]

#: Audiences a skill can be shared with, read from ActorKind rather than listed again.
SharedAudience = Literal[tuple(kind.value for kind in ActorKind if kind is not ActorKind.OWNER)]  # type: ignore[valid-type]

AVAILABLE_TO_DESCRIPTION = (
    "Who besides you may use the skill. `visitor` is a signed-in widget user, "
    "`guest` is a widget user who gave only an email."
)

#: Marks a field whose value names other resources in the blueprint, and the kind they must be.
REF_KIND = "x-ref-kind"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParamSpec(Strict):
    """A value the person running the blueprint fills in."""

    type: Literal["string", "text", "url", "boolean", "integer", "choice"] = Field(
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
    description: str | None = Field(
        None, description="What this resource is for. Stored as the resource's description where it has one."
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


ResourceSpec = Union[KnowledgeBaseSpec, AgentSpec, WidgetKeySpec]
Resource = Annotated[ResourceSpec, Field(discriminator="kind")]
RESOURCE_SPECS: tuple[type[ResourceBase], ...] = (KnowledgeBaseSpec, AgentSpec, WidgetKeySpec)


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


class Blueprint(Strict):
    """A description of a solution on InnomightLabs: the resources to create and how they connect."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["innomight/v1"] = Field(
        alias="apiVersion", description="Which version of the blueprint rules this document follows."
    )
    kind: Literal["Blueprint"] = Field(description="Always Blueprint. Marks the document type.")
    metadata: Metadata = Field(description="Who the blueprint is and what it's for.")
    params: dict[ResourceName, ParamSpec] = Field(
        default_factory=dict,
        description="Values the person running the blueprint fills in. Each becomes an input in the run form.",
    )
    resources: dict[ResourceName, Resource] = Field(
        min_length=1,
        description="Everything the blueprint creates. The key is the resource's local name, used for references.",
    )
    outputs: dict[ResourceName, OutputSpec] = Field(
        default_factory=dict, description="Values shown after a successful apply, such as the embed snippet."
    )
