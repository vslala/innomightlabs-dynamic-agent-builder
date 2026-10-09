from html import escape
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    AppliedResource,
    ApplyContext,
    Change,
    Existing,
    ManagedKind,
    NotFound,
    PlanContext,
)
from src.blueprints.spec import WidgetKeySpec
from src.config import settings


def origin_of(url: str) -> str | None:
    """`https://example.com/about` → `https://example.com`; None for anything that isn't a web address."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc.lower()}"


def origins(spec: WidgetKeySpec) -> list[str]:
    return sorted({origin for origin in map(origin_of, spec.allowed_origins) if origin})


def embed_snippet(public_key: str) -> str:
    return f'<script src="{escape(settings.embed_loader_url)}" data-api-key="{escape(public_key)}" async></script>'


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
        agent = ctx.matched.get(spec.agent)
        keys = ApiKeyRepository().find_all_by_agent(agent.id) if agent else []
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

    def differences(self, name: str, spec: WidgetKeySpec, existing: Existing, ctx: PlanContext) -> list[str]:
        key: AgentApiKey = existing.record
        changes = []
        if spec.name and spec.name != key.name:
            changes.append(f"rename to '{spec.name}'")
        if origins(spec) != sorted(key.allowed_origins):
            changes.append("allow it on " + ", ".join(origins(spec)))
        if spec.allow_guests != key.allow_guests:
            changes.append("let guests chat with just an email" if spec.allow_guests else "ask visitors to sign in")
        return changes

    def describe(self, name: str, spec: WidgetKeySpec) -> str:
        guests = ", guests allowed" if spec.allow_guests else ""
        return f"Create a widget key for {spec.agent} on {', '.join(spec.allowed_origins)}{guests}"

    def apply(self, name: str, spec: WidgetKeySpec, ctx: ApplyContext) -> AppliedResource:
        agent = ctx.applied[spec.agent]
        key = ApiKeyRepository().save(AgentApiKey(
            agent_id=agent.id,
            name=spec.name or f"{agent.attributes['name']} widget",
            allowed_origins=origins(spec),
            allow_guests=spec.allow_guests,
            created_by=ctx.user_email,
        ))
        return self._applied(name, key)

    def update(self, name: str, spec: WidgetKeySpec, change: Change, ctx: ApplyContext) -> AppliedResource:
        previous: AgentApiKey = change.existing.record  # type: ignore[union-attr]
        # The same key, so the snippet already on the person's site keeps working.
        key = ApiKeyRepository().save(previous.model_copy(update={
            "name": spec.name or previous.name,
            "allowed_origins": origins(spec),
            "allow_guests": spec.allow_guests,
        }))
        applied = self._applied(name, key)
        applied.previous = previous
        return applied

    def kept(self, name: str, change: Change) -> AppliedResource:
        return self._applied(name, change.existing.record)  # type: ignore[union-attr]

    def _applied(self, name: str, key: AgentApiKey) -> AppliedResource:
        return AppliedResource(
            name=name,
            kind=self.kind,
            id=key.key_id,
            attributes={"id": key.key_id, "public_key": key.public_key, "snippet": embed_snippet(key.public_key)},
            cleanup={"agent_id": [key.agent_id]},
        )

    def delete(self, change: Change, ctx: ApplyContext) -> None:
        key: AgentApiKey = change.existing.record  # type: ignore[union-attr]
        ApiKeyRepository().delete_by_id(key.agent_id, key.key_id)

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        ApiKeyRepository().delete_by_id(applied.cleanup["agent_id"][0], applied.id)

    def restore(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        ApiKeyRepository().save(applied.previous)
