"""Reading blueprint YAML: safe loading, size limits, and a path → line map for error messages."""

from typing import Any

import yaml  # type: ignore[import-untyped,unused-ignore]

from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.config import settings


def parse_yaml(text: str) -> tuple[Any, dict[str, int]]:
    """The document and the 1-based line of every path in it. Raises BlueprintInvalid."""
    if len(text.encode("utf-8")) > settings.blueprint_max_bytes:
        raise BlueprintInvalid([BlueprintIssue(
            path="",
            message=f"The blueprint is larger than {settings.blueprint_max_bytes // 1024} KB.",
        )])
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise BlueprintInvalid([BlueprintIssue(
                    path="",
                    line=event.start_mark.line + 1,
                    message="YAML anchors and aliases (& and *) aren't allowed in a blueprint.",
                    hint="Write the value out in full.",
                )])
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise BlueprintInvalid([BlueprintIssue(
            path="",
            line=mark.line + 1 if mark else None,
            message=f"This isn't valid YAML: {getattr(e, 'problem', None) or e}",
            hint="Check the indentation and that every `key: value` has a space after the colon.",
        )]) from e

    lines: dict[str, int] = {}
    if node is not None:
        _index_lines(node, "", lines)
    return data, lines


def join_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if parent else str(key)


def _index_lines(node: yaml.Node, path: str, lines: dict[str, int]) -> None:
    lines.setdefault(path, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            child = join_path(path, str(key_node.value))
            lines[child] = key_node.start_mark.line + 1
            _index_lines(value_node, child, lines)
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            _index_lines(item, join_path(path, index), lines)
