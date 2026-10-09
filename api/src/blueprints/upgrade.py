"""Older blueprint documents, read as the current version.

A kit keeps every version it applied, and rolling back replays one, so a document written to an earlier version
must still be read. Each upgrade turns one version into the next.

- `innomight/v1` said removals explicitly: `remove: true` on a resource, and `remove_knowledge_bases`,
  `remove_mcp_connections` and `remove_skills` on an agent. In v2 a kit's blueprint is the whole of what it should
  hold, so leaving something out removes it. A v1 document's desired state is what it keeps: resources marked
  `remove` are dropped, and so are the removal lists.
"""

from __future__ import annotations

from typing import Any, Callable

from src.blueprints.spec import API_VERSION

V1 = "innomight/v1"
REMOVAL_LISTS = ("remove_knowledge_bases", "remove_mcp_connections", "remove_skills")


def _v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    resources = document.get("resources")
    if isinstance(resources, dict):
        document["resources"] = {
            name: {key: value for key, value in spec.items() if key not in ("remove", *REMOVAL_LISTS)}
            if isinstance(spec, dict) else spec
            for name, spec in resources.items()
            if not (isinstance(spec, dict) and spec.get("remove"))
        }
    document["apiVersion"] = API_VERSION
    return document


#: Each older version, and how it becomes the next.
UPGRADES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {V1: _v1_to_v2}


def upgrade(document: dict[str, Any]) -> dict[str, Any]:
    """The document as the current version. A current or unknown version is returned as it is; the validator
    reports an unknown one."""
    while document.get("apiVersion") in UPGRADES:
        document = UPGRADES[document["apiVersion"]](dict(document))
    return document
