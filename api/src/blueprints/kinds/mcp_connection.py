"""MCP connections in a blueprint: a ready-made server (a preset), such as Tavily web search, that agents use.

A connection belongs to the account and holds the person's sign-in, so a blueprint never creates one: the
person connects it, through the card the system shows when Ada plans (`builder/connections.py`), and the
blueprint finds that connection and links agents to it. Applying the same blueprint again finds it again.
"""

from typing import Optional

from src.blueprints.issues import BlueprintIssue
from src.blueprints.kinds.base import (
    AppliedResource,
    Change,
    Existing,
    NotFound,
    PlanContext,
    ResourceKind,
)
from src.blueprints.spec import McpConnectionSpec
from src.connectors.mcp.models import MCPConnection
from src.connectors.mcp.providers import PROVIDERS
from src.connectors.mcp.repository import get_mcp_connection_repository
from src.connectors.mcp.service import get_mcp_connector_service


def is_ready(connection: MCPConnection) -> bool:
    """Signed in, with every input the preset needs, and switched on."""
    response = get_mcp_connector_service().get_connection(connection.owner_email, connection.mcp_id)
    return connection.enabled and response.setup_state == "ready"


def connection_for(spec: McpConnectionSpec, user_email: str) -> Optional[MCPConnection]:
    """The account's connection this spec means: the one with its id, else the ready one for its provider (by name
    when there's more than one)."""
    repository = get_mcp_connection_repository()
    if spec.id:
        return repository.find_connection(user_email, spec.id)
    same = [connection for connection in repository.list_connections(user_email) if connection.provider_key == spec.provider]
    if spec.name:
        same = [connection for connection in same if connection.name == spec.name] or same
    ready = [connection for connection in same if is_ready(connection)]
    candidates = ready or same
    return candidates[0] if candidates else None


def provider_name(spec: McpConnectionSpec) -> str:
    provider = PROVIDERS.get(spec.provider or "")
    return provider.display_name if provider else (spec.name or "MCP server")


class McpConnectionKind(ResourceKind[McpConnectionSpec]):
    kind = "McpConnection"
    label = "MCP connection"
    use_when = (
        "The agent needs tools from another service: search the web, read web pages, or work in Jira, GitHub or "
        "Canva."
    )
    deletes = "every agent using it loses its tools"
    spec_model = McpConnectionSpec
    exposes = ("id", "name")

    def validate(self, name: str, spec: McpConnectionSpec) -> list[BlueprintIssue]:
        path = f"resources.{name}"
        if not spec.provider and not spec.id:
            return [BlueprintIssue(
                path=f"{path}.provider",
                message="Say which MCP server to connect.",
                hint=f"Set `provider` to one of: {', '.join(PROVIDERS)}.",
            )]
        if spec.remove:
            return [BlueprintIssue(
                path=f"{path}.remove",
                message="A blueprint can't delete an MCP connection; it belongs to the whole account.",
                hint="Use the agent's `remove_mcp_connections` to take it away from one agent.",
            )]
        return []

    def find_existing(self, name: str, spec: McpConnectionSpec, ctx: PlanContext) -> Optional[Existing]:
        connection = connection_for(spec, ctx.user_email)
        if connection is None:
            if spec.id:
                raise NotFound(f"There's no MCP connection with id '{spec.id}' in your account.")
            return None
        return Existing(id=connection.mcp_id, record=connection, matched_by="id" if spec.id else "name")

    def check(self, name: str, spec: McpConnectionSpec, change: Change, ctx: PlanContext) -> list[BlueprintIssue]:
        # The system asks the person to connect before planning, so this only catches a sign-in that lapsed since.
        connection: Optional[MCPConnection] = change.existing.record if change.existing else None
        if connection is None or not is_ready(connection):
            return [BlueprintIssue(
                path=f"resources.{name}.provider",
                message=f"{provider_name(spec)} isn't connected to your account yet.",
                hint="Connect it from the card in this chat, or on the Connectors page.",
            )]
        return []

    def describe(self, name: str, spec: McpConnectionSpec) -> str:
        return f"Use your {provider_name(spec)} connection"

    def kept(self, name: str, change: Change) -> AppliedResource:
        connection: MCPConnection = change.existing.record  # type: ignore[union-attr]
        return AppliedResource(
            name=name,
            kind=self.kind,
            id=connection.mcp_id,
            attributes={"id": connection.mcp_id, "name": connection.name},
        )

    def page_sections(self) -> list[str]:
        lines = [
            "### Providers",
            "| `provider` | What it gives an agent | Connecting |",
            "| --- | --- | --- |",
        ]
        for key, provider in PROVIDERS.items():
            how = "the person signs in from a card in the chat" if not provider.missing_inputs({}) else (
                "needs set-up on the Connectors page first"
            )
            lines.append(f"| `{key}` | {provider.description} | {how} |")
        return [
            *lines,
            "",
            "Link it to agents with their `mcp_connections`. You never connect it yourself: when you plan, the "
            "system asks the person to sign in if the account isn't connected yet.",
            "",
        ]
