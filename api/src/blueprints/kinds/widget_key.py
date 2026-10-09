from dataclasses import dataclass
from html import escape
from typing import Any, ClassVar, Mapping, Optional
from uuid import uuid4

from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.commands import Command, Reversibility, Undo, Use, undo_action
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    AppliedResource,
    ApplyContext,
    Existing,
    ManagedKind,
    NotFound,
    PlanContext,
)
from src.blueprints.reconcile import Outcome
from src.blueprints.spec import WidgetKeySpec, origin_of, origins_of
from src.config import settings


def origins(spec: WidgetKeySpec) -> list[str]:
    return origins_of(spec.allowed_origins)


def embed_snippet(public_key: str) -> str:
    return f'<script src="{escape(settings.embed_loader_url)}" data-api-key="{escape(public_key)}" async></script>'


def _applied(name: str, key: AgentApiKey) -> AppliedResource:
    return AppliedResource(
        name=name,
        kind="WidgetKey",
        id=key.key_id,
        attributes={"id": key.key_id, "public_key": key.public_key, "snippet": embed_snippet(key.public_key)},
    )


def _find(agent_id: str, key_id: str) -> Optional[AgentApiKey]:
    return next((key for key in ApiKeyRepository().find_all_by_agent(agent_id) if key.key_id == key_id), None)


# --- Commands -----------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class CreateWidgetKey(Command):
    agent: str
    key_name: Optional[str]
    allowed_origins: list[str]
    allow_guests: bool
    #: Chosen when it's prepared, so the undo knows it even if the apply stops before the create returns.
    key_id: str = ""

    reversibility: ClassVar[Reversibility] = Reversibility.COMPENSATABLE
    establishes: ClassVar[bool] = True
    creates: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        self.key_id = self.key_id or str(uuid4())
        return Undo("delete_widget_key", {"agent_id": ctx.applied[self.agent].id, "key_id": self.key_id})

    def run(self, ctx: ApplyContext) -> None:
        agent = ctx.applied[self.agent]
        key = ApiKeyRepository().save(AgentApiKey(
            key_id=self.key_id,
            agent_id=agent.id,
            name=self.key_name or f"{agent.attributes['name']} widget",
            allowed_origins=self.allowed_origins,
            allow_guests=self.allow_guests,
            created_by=ctx.user_email,
        ))
        ctx.applied[self.resource] = _applied(self.resource, key)


@undo_action("delete_widget_key")
def _delete_widget_key(args: dict[str, Any], user_email: str) -> None:
    ApiKeyRepository().delete_by_id(args["agent_id"], args["key_id"])


@dataclass(kw_only=True)
class SaveWidgetKey(Command):
    """The same key, so the snippet already on the person's site keeps working."""

    agent_id: str
    key_id: str
    fields: dict[str, Any]

    establishes: ClassVar[bool] = True

    def prepare(self, ctx: ApplyContext) -> Optional[Undo]:
        current = _find(self.agent_id, self.key_id)
        before = {key: getattr(current, key) for key in self.fields} if current else {}
        return Undo("restore_widget_key", {"agent_id": self.agent_id, "key_id": self.key_id, "fields": before})

    def run(self, ctx: ApplyContext) -> None:
        ctx.applied[self.resource] = _applied(self.resource, _save_fields(self.agent_id, self.key_id, self.fields))


def _save_fields(agent_id: str, key_id: str, fields: dict[str, Any]) -> AgentApiKey:
    current = _find(agent_id, key_id)
    if current is None:
        raise RuntimeError("The widget key was deleted since the plan. Plan again.")
    return ApiKeyRepository().save(current.model_copy(update=fields))


@undo_action("restore_widget_key")
def _restore_widget_key(args: dict[str, Any], user_email: str) -> None:
    if args["fields"]:
        _save_fields(args["agent_id"], args["key_id"], args["fields"])


@dataclass(kw_only=True)
class DeleteWidgetKey(Command):
    agent_id: str
    key_id: str

    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True

    def run(self, ctx: ApplyContext) -> None:
        ApiKeyRepository().delete_by_id(self.agent_id, self.key_id)


# --- The kind -----------------------------------------------------------------------------------------------


class WidgetKeyKind(ManagedKind[WidgetKeySpec]):
    kind = "WidgetKey"
    label = "Chat widget"
    use_when = "Put an agent on a website as a chat bubble, or let visitors chat without signing in."
    deletes = "the chat widget stops working on every site that uses this key"
    spec_model = WidgetKeySpec
    exposes = ("id", "public_key", "snippet")
    export_name = "widget"

    def observe(self, record: AgentApiKey, names: Mapping[str, str]) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": record.key_id,
            "agent": names.get(record.agent_id, record.agent_id),
            "name": record.name,
            "allowed_origins": list(record.allowed_origins),
            "allow_guests": record.allow_guests,
        }

    def for_agent(self, agent_id: str) -> list[AgentApiKey]:
        """The agent's keys a blueprint can describe. A key that works on any site has no origins to write down; a
        blueprint never makes those, so they're left alone."""
        return [key for key in ApiKeyRepository().find_all_by_agent(agent_id) if key.allowed_origins]

    def applied(self, name: str, record: AgentApiKey) -> AppliedResource:
        return _applied(name, record)

    def title(self, name: str, spec: WidgetKeySpec, resources: dict[str, Any]) -> str:
        # The key's dashboard label defaults to "<agent name> widget" too.
        return spec.name or f"{getattr(resources.get(spec.agent), 'name', None) or spec.agent} widget"

    def card_details(self, spec: WidgetKeySpec) -> list[str]:
        return [
            "On " + ", ".join(spec.allowed_origins),
            "Guests can chat with just an email" if spec.allow_guests else "Visitors sign in with Google",
        ]

    def validate(self, name: str, spec: WidgetKeySpec) -> list[BlueprintIssue]:
        return [
            BlueprintIssue(
                path=f"resources.{name}.allowed_origins[{index}]",
                message=f"'{origin}' isn't a web address.",
                hint="Use the site's address, such as https://example.com.",
            )
            for index, origin in enumerate(spec.allowed_origins)
            if "{{" not in origin and origin_of(origin) is None
        ]

    def find_existing(self, name: str, spec: WidgetKeySpec, ctx: PlanContext) -> Optional[Existing]:
        matched = ctx.matched.get(spec.agent)
        agent_id = matched.id if matched else ctx.pinned.get(spec.agent)
        keys = ApiKeyRepository().find_all_by_agent(agent_id) if agent_id else []
        if spec.id:
            key = next((key for key in keys if key.key_id == spec.id), None)
            if key is None:
                raise NotFound(f"There's no widget key with id '{spec.id}' on that agent.")
            return Existing(id=key.key_id, record=key, matched_by="id")
        if spec.name:
            same = [key for key in keys if key.name == spec.name]
        else:
            # Unnamed keys are "<agent name> widget"; an agent with a single key is that key, renamed or not.
            same = keys if len(keys) == 1 else [key for key in keys if key.name.endswith(" widget")]
        return Existing(id=same[0].key_id, record=same[0], matched_by="name") if len(same) == 1 else None

    def commands(
        self, name: str, spec: WidgetKeySpec, existing: Optional[Existing], outcome: Outcome, ctx: PlanContext
    ) -> list[Command]:
        if existing is None:
            return [CreateWidgetKey(
                resource=name,
                uses=frozenset({spec.agent}),
                agent=spec.agent,
                key_name=spec.name,
                allowed_origins=origins(spec),
                allow_guests=spec.allow_guests,
            )]
        key: AgentApiKey = existing.record
        fields = outcome.values(WidgetKeySpec)
        if "allowed_origins" in fields:
            fields["allowed_origins"] = origins(spec)  # stored as origins, as compared
        if not fields:
            return [Use(resource=name, uses=frozenset({spec.agent}), applied=_applied(name, key))]
        return [SaveWidgetKey(
            resource=name,
            uses=frozenset({spec.agent}),
            agent_id=key.agent_id,
            key_id=key.key_id,
            fields=fields,
            says=outcome.says(),
        )]

    def delete_commands(self, name: str, spec: WidgetKeySpec, existing: Existing, removal: str) -> list[Command]:
        key: AgentApiKey = existing.record
        return [DeleteWidgetKey(
            resource=name, uses=frozenset({spec.agent}), agent_id=key.agent_id, key_id=key.key_id, removal=removal
        )]

    def describe(self, name: str, spec: WidgetKeySpec) -> str:
        guests = ", guests allowed" if spec.allow_guests else ""
        return f"Create a widget key for {spec.agent} on {', '.join(spec.allowed_origins)}{guests}"
