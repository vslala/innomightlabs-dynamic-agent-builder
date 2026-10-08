from html import escape
from urllib.parse import urlsplit

from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import AppliedResource, ApplyContext, ResourceKind
from src.blueprints.spec import WidgetKeySpec
from src.config import settings


def origin_of(url: str) -> str | None:
    """`https://example.com/about` → `https://example.com`; None for anything that isn't a web address."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc.lower()}"


def embed_snippet(public_key: str) -> str:
    return f'<script src="{escape(settings.embed_loader_url)}" data-api-key="{escape(public_key)}" async></script>'


class WidgetKeyKind(ResourceKind[WidgetKeySpec]):
    kind = "WidgetKey"
    spec_model = WidgetKeySpec
    exposes = ("id", "public_key", "snippet")

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

    def describe(self, name: str, spec: WidgetKeySpec) -> str:
        guests = ", guests allowed" if spec.allow_guests else ""
        return f"Create a widget key for {spec.agent} on {', '.join(spec.allowed_origins)}{guests}"

    def apply(self, name: str, spec: WidgetKeySpec, ctx: ApplyContext) -> AppliedResource:
        agent = ctx.applied[spec.agent]
        key = ApiKeyRepository().save(AgentApiKey(
            agent_id=agent.id,
            name=spec.name or f"{agent.attributes['name']} widget",
            allowed_origins=sorted({origin for origin in map(origin_of, spec.allowed_origins) if origin}),
            allow_guests=spec.allow_guests,
            created_by=ctx.user_email,
        ))
        return AppliedResource(
            name=name,
            kind=self.kind,
            id=key.key_id,
            attributes={"id": key.key_id, "public_key": key.public_key, "snippet": embed_snippet(key.public_key)},
            cleanup={"agent_id": [agent.id]},
        )

    def rollback(self, applied: AppliedResource, ctx: ApplyContext) -> None:
        ApiKeyRepository().delete_by_id(applied.cleanup["agent_id"][0], applied.id)
