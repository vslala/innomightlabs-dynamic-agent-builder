"""An existing agent written out as a blueprint, so it can be changed and applied again.

Every resource carries its `id`, so applying the exported blueprint as it is changes nothing, and applying an
edited one updates the same agent, knowledge bases and widget keys instead of creating new ones.
"""

import re
from typing import Any, Optional

import yaml  # type: ignore[import-untyped,unused-ignore]

from src.agents.repository import AgentRepository
from src.blueprints.kinds import kind_for
from src.blueprints.kinds.agent import AgentKind
from src.blueprints.kinds.widget_key import WidgetKeyKind
from src.blueprints.spec import API_VERSION


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "agent"


def _numbered(base: str, index: int) -> str:
    return base if index == 0 else f"{base}_{index + 1}"


def export_agent(agent_id: str, user_email: str) -> Optional[str]:
    """The agent as blueprint YAML, or None if it isn't the person's: the resources it links to, the agent, and its
    widget keys, each written by its own kind's `observe`."""
    agent = AgentRepository().find_agent_by_id(agent_id, user_email)
    if agent is None:
        return None
    agent_kind, widget_kind = AgentKind(), WidgetKeyKind()

    # Each resource's blueprint name, by id, so the ones naming it can say so.
    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    records: list[tuple[str, str, Any]] = []
    keys = [(widget_kind.kind, key.key_id, key) for key in widget_kind.for_agent(agent_id)]
    for kind, resource_id, record in [
        *agent_kind.linked(agent_id, user_email), (agent_kind.kind, agent_id, agent), *keys,
    ]:
        base = kind_for(kind).export_name
        names[resource_id] = _numbered(base, counts.get(base, 0))
        counts[base] = counts.get(base, 0) + 1
        records.append((kind, names[resource_id], record))

    resources = {name: kind_for(kind).observe(record, names) for kind, name, record in records}

    outputs: dict[str, Any] = {"agent_id": {"description": "The agent in the dashboard.", "value": "{{ resources.agent.id }}"}}
    if keys:
        outputs["snippet"] = {
            "description": "Paste this before </body> on every page of your site.",
            "value": f"{{{{ resources.{names[keys[0][1]]}.snippet }}}}",
        }

    document = {
        "apiVersion": API_VERSION,
        "kind": "Blueprint",
        "metadata": {
            "name": _slug(agent.agent_name),
            "title": agent.agent_name,
            **({"description": agent.agent_description} if agent.agent_description else {}),
        },
        "resources": resources,
        "outputs": outputs,
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def with_ids(text: str, ids: dict[str, str]) -> str:
    """The blueprint with each named resource pinned to the id it was built as, so the next apply updates it."""
    document = yaml.safe_load(text)
    for name, resource_id in ids.items():
        resource = document.get("resources", {}).get(name)
        if isinstance(resource, dict):
            # Put `id` right after `kind`, where a reader expects it.
            pinned = {"kind": resource.get("kind"), "id": resource_id}
            pinned.update({key: value for key, value in resource.items() if key not in ("kind", "id")})
            document["resources"][name] = pinned
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
