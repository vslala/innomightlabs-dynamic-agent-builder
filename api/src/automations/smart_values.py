"""Smart value resolution for automation templates and condition expressions.

One resolver backs prompt templates, skill action arguments, and condition
expressions so they all understand the same references:

    {{ input.topic }}
    {{ trigger.type }}
    {{ steps.find_senders.output.response_text }}
    {{ last.output.response_text }}
    {{ steps.find_senders.output.events | length }}
    {{ steps.find_senders.output.summary | default("nothing found") }}

Legacy JSON-context paths keep working so saved automations are unaffected:

    {{ $.input }}
    {{ $.nodes.action-bf61da39-….output.response_text }}

The language is deliberately closed: dot paths, list indexes, and three filters.
No arbitrary expressions are evaluated.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

TOKEN_PATTERN = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

CONTEXT_ROOTS = frozenset({"input", "trigger", "steps", "nodes", "last", "execution"})

MISSING = object()

TOKEN_STATUS_RESOLVED = "resolved"
TOKEN_STATUS_EMPTY = "empty"
TOKEN_STATUS_UNKNOWN = "unknown"
TOKEN_STATUS_INVALID = "invalid"

PREVIEW_VALUE_LIMIT = 240


@dataclass(frozen=True)
class SmartValueFilter:
    name: str
    argument: str | None = None


@dataclass(frozen=True)
class SmartValueToken:
    raw: str
    path: str
    filters: tuple[SmartValueFilter, ...] = ()
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class SmartValueTokenPreview:
    token: str
    path: str
    status: str
    value: str | None = None


@dataclass(frozen=True)
class SmartValuePreview:
    rendered: str
    tokens: list[SmartValueTokenPreview] = field(default_factory=list)


def parse_tokens(template: str) -> list[SmartValueToken]:
    tokens: list[SmartValueToken] = []
    for match in TOKEN_PATTERN.finditer(template):
        path, filters = _split_filters(match.group(1).strip())
        tokens.append(
            SmartValueToken(
                raw=match.group(0),
                path=path,
                filters=filters,
                start=match.start(),
                end=match.end(),
            )
        )
    return tokens


def _split_filters(expression: str) -> tuple[str, tuple[SmartValueFilter, ...]]:
    """Split ``path | filter | filter(arg)`` without breaking quoted arguments."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in expression:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            current.append(char)
            continue
        if char == "|":
            segments.append("".join(current))
            current = []
            continue
        current.append(char)
    segments.append("".join(current))

    path = segments[0].strip()
    filters = tuple(_parse_filter(segment.strip()) for segment in segments[1:] if segment.strip())
    return path, filters


def _parse_filter(segment: str) -> SmartValueFilter:
    match = re.fullmatch(r"([a-z_]+)\s*\((.*)\)", segment, re.DOTALL)
    if not match:
        return SmartValueFilter(name=segment)
    return SmartValueFilter(name=match.group(1), argument=_literal(match.group(2).strip()))


def _literal(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "None"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


class SmartValueResolver:
    """Resolves smart values against one automation run context."""

    def __init__(self, context: dict[str, Any] | None = None):
        self.context: dict[str, Any] = context or {}

    def render_template(self, template: str) -> str:
        """Render a template to text. Missing values become an empty string."""
        if not template:
            return template

        def replace(match: re.Match[str]) -> str:
            path, filters = _split_filters(match.group(1).strip())
            return _stringify(self._apply_filters(self._resolve_path(path), filters))

        return TOKEN_PATTERN.sub(replace, template)

    def render_value(self, value: Any) -> Any:
        """Render nested action arguments, preserving types for whole-token strings."""
        if isinstance(value, dict):
            return {key: self.render_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render_value(item) for item in value]
        if isinstance(value, str):
            return self._render_string(value)
        return value

    def resolve(self, expression: str) -> Any:
        """Resolve a bare path or a single ``{{ … }}`` token to its raw value."""
        expression = expression.strip()
        match = re.fullmatch(r"\{\{(.*)\}\}", expression, re.DOTALL)
        if match:
            expression = match.group(1).strip()
        path, filters = _split_filters(expression)
        return self._apply_filters(self._resolve_path(path), filters)

    def evaluate_condition(self, expression: str) -> bool:
        expression = (expression or "").strip()
        if not expression:
            return False
        for operator in ("==", "!="):
            left, right = _split_comparison(expression, operator)
            if left is None or right is None:
                continue
            equal = self.resolve(left) == _comparison_operand(self, right)
            return equal if operator == "==" else not equal
        return bool(self.resolve(expression))

    def preview(self, template: str) -> SmartValuePreview:
        """Render a template and report per-token resolution status for the editor."""
        previews: list[SmartValueTokenPreview] = []
        for token in parse_tokens(template):
            resolved = self._apply_filters(
                self._resolve_path(token.path, default=MISSING), token.filters
            )
            if not token.path:
                status = TOKEN_STATUS_INVALID
                value = None
            elif resolved is MISSING or resolved is None:
                status = TOKEN_STATUS_UNKNOWN
                value = None
            else:
                rendered = _stringify(resolved)
                status = TOKEN_STATUS_RESOLVED if rendered else TOKEN_STATUS_EMPTY
                value = rendered[:PREVIEW_VALUE_LIMIT] or None
            previews.append(
                SmartValueTokenPreview(
                    token=token.raw,
                    path=token.path,
                    status=status,
                    value=value,
                )
            )
        return SmartValuePreview(rendered=self.render_template(template), tokens=previews)

    def _render_string(self, value: str) -> Any:
        whole = re.fullmatch(r"\s*\{\{(.*)\}\}\s*", value, re.DOTALL)
        if whole:
            path, filters = _split_filters(whole.group(1).strip())
            return self._apply_filters(self._resolve_path(path), filters)

        def replace(match: re.Match[str]) -> str:
            path, filters = _split_filters(match.group(1).strip())
            return _stringify(self._apply_filters(self._resolve_path(path), filters))

        return TOKEN_PATTERN.sub(replace, value)

    def _apply_filters(self, value: Any, filters: tuple[SmartValueFilter, ...]) -> Any:
        for item in filters:
            value = self._apply_filter(value, item)
        return value

    def _apply_filter(self, value: Any, item: SmartValueFilter) -> Any:
        if item.name == "json":
            return json.dumps(value if value is not MISSING else None)
        if item.name == "length":
            if isinstance(value, (str, list, dict, tuple)):
                return len(value)
            return 0
        if item.name == "default":
            missing = value is MISSING or value is None or value == ""
            return item.argument if missing else value
        return value

    def _resolve_path(self, path: str, default: Any = None) -> Any:
        path = path.strip()
        if not path:
            return default
        if path == "$":
            return self.context
        if path.startswith("$."):
            return _walk(self.context, path[2:].split("."), default)

        segments = path.split(".")
        root = segments[0]
        if root not in CONTEXT_ROOTS:
            return default
        if root == "last":
            step = self._last_step()
            if step is None:
                return default
            return _walk(step, segments[1:], default)
        return _walk(self.context.get(root), segments[1:], default)

    def _last_step(self) -> Any:
        execution = self.context.get("execution")
        if not isinstance(execution, dict):
            return None
        alias = execution.get("last_step_alias")
        steps = self.context.get("steps")
        if alias and isinstance(steps, dict) and alias in steps:
            return steps[alias]
        node_id = execution.get("last_node_id")
        nodes = self.context.get("nodes")
        if node_id and isinstance(nodes, dict):
            return nodes.get(node_id)
        return None


def _split_comparison(expression: str, operator: str) -> tuple[str | None, str | None]:
    """Find ``operator`` outside quotes so string literals can contain it."""
    quote: str | None = None
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if expression.startswith(operator, index):
            return expression[:index].strip(), expression[index + len(operator) :].strip()
        index += 1
    return None, None


def _comparison_operand(resolver: SmartValueResolver, raw: str) -> Any:
    """A quoted or numeric right-hand side is a literal; anything else is a path."""
    literal = _literal(raw)
    if literal != raw or not raw:
        return literal
    resolved = resolver._resolve_path(raw, default=MISSING)
    return raw if resolved is MISSING else resolved


def _walk(value: Any, segments: list[str], default: Any = None) -> Any:
    current = value
    for segment in segments:
        if not segment:
            continue
        if isinstance(current, dict):
            if segment not in current:
                return default
            current = current[segment]
        elif isinstance(current, (list, tuple)) and segment.lstrip("-").isdigit():
            index = int(segment)
            if not -len(current) <= index < len(current):
                return default
            current = current[index]
        else:
            return default
    return default if current is None else current


def _stringify(value: Any) -> str:
    if value is MISSING or value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value)
    return str(value)
