"""Stable, human-readable aliases for automation nodes.

``node_id`` stays the execution identity. The alias is the user-facing identity
used by smart values, for example ``{{ steps.find_senders.output.response_text }}``.
Aliases survive renames, so templates keep resolving when a step name changes.
"""

from __future__ import annotations

import re

from src.automations.models import AutomationNode, AutomationNodeType

ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

RESERVED_ALIASES = frozenset(
    {
        "current",
        "env",
        "execution",
        "input",
        "last",
        "nodes",
        "run",
        "steps",
        "trigger",
    }
)

ALIASABLE_NODE_TYPES = frozenset({AutomationNodeType.ACTION, AutomationNodeType.CONDITION})

MAX_ALIAS_LENGTH = 63


def is_aliasable(node: AutomationNode) -> bool:
    """Start and final nodes are addressed through ``input`` and ``trigger`` instead."""
    return node.type in ALIASABLE_NODE_TYPES


def slugify_alias(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"step_{slug}".rstrip("_")
    return slug[:MAX_ALIAS_LENGTH]


def unique_alias(preferred: str, taken: set[str]) -> str:
    base = f"{preferred}_step" if preferred in RESERVED_ALIASES else preferred
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base[: MAX_ALIAS_LENGTH - 4]}_{suffix}"
        suffix += 1
    return candidate


def assign_missing_aliases(nodes: list[AutomationNode]) -> list[AutomationNode]:
    """Backfill aliases for aliasable nodes that do not have one yet.

    Called on every save so legacy automations acquire aliases on first edit
    without a migration job. Existing aliases are never rewritten.
    """
    taken = {node.alias for node in nodes if node.alias}
    for node in nodes:
        if node.alias or not is_aliasable(node):
            continue
        alias = unique_alias(slugify_alias(node.name), taken)
        node.alias = alias
        taken.add(alias)
    return nodes


def alias_errors(nodes: list[AutomationNode]) -> list[str]:
    """Format, reserved-word, and uniqueness problems for explicitly set aliases."""
    errors: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        alias = node.alias
        if not alias:
            continue
        if not ALIAS_PATTERN.match(alias):
            errors.append(
                f"Reference name '{alias}' must start with a letter and use only "
                "lowercase letters, digits, and underscores"
            )
        elif alias in RESERVED_ALIASES:
            errors.append(f"Reference name '{alias}' is reserved")
        elif alias in seen:
            errors.append(f"Reference name '{alias}' is used by more than one step")
        seen.add(alias)
    return errors
