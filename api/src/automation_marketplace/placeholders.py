from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PLACEHOLDER_RE = re.compile(r"{{\s*(skills|inputs)\.([a-zA-Z0-9_\-]+)(?:\.([a-zA-Z0-9_\-]+))?\s*}}")


@dataclass(frozen=True)
class PlaceholderContext:
    skills: dict[str, dict[str, Any]]
    inputs: dict[str, Any]


class PlaceholderResolutionError(ValueError):
    pass


class MarketplacePlaceholderRenderer:
    def render(self, value: Any, context: PlaceholderContext) -> Any:
        if isinstance(value, str):
            return self._render_string(value, context)
        if isinstance(value, list):
            return [self.render(item, context) for item in value]
        if isinstance(value, dict):
            return {key: self.render(item, context) for key, item in value.items()}
        return value

    def _render_string(self, value: str, context: PlaceholderContext) -> Any:
        full_match = PLACEHOLDER_RE.fullmatch(value)
        if full_match:
            return self._resolve(full_match, context)

        def replace(match: re.Match[str]) -> str:
            resolved = self._resolve(match, context)
            return "" if resolved is None else str(resolved)

        return PLACEHOLDER_RE.sub(replace, value)

    def _resolve(self, match: re.Match[str], context: PlaceholderContext) -> Any:
        source, key, field = match.group(1), match.group(2), match.group(3)
        if source == "inputs":
            if key not in context.inputs:
                raise PlaceholderResolutionError(f"Missing import input: {key}")
            if field:
                raise PlaceholderResolutionError(f"Import input placeholders do not support field access: {key}.{field}")
            return context.inputs[key]

        if key not in context.skills:
            raise PlaceholderResolutionError(f"Missing imported skill: {key}")
        skill = context.skills[key]
        if not field:
            raise PlaceholderResolutionError(f"Skill placeholder requires a field: {key}")
        if field not in skill:
            raise PlaceholderResolutionError(f"Missing imported skill field: {key}.{field}")
        return skill[field]

