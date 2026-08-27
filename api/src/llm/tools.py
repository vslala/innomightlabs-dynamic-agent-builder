"""Provider-neutral tool definition normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_INPUT_SCHEMA = {"type": "object", "properties": {}}


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_INPUT_SCHEMA))
    strict: bool | None = None

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }
        if self.strict is not None:
            payload["strict"] = self.strict
        return payload

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_bedrock(self) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": self.name,
                "description": self.description,
                "inputSchema": {"json": self.input_schema},
            }
        }


def normalize_tool_definitions(tools: list[dict[Any, Any]] | None) -> list[ToolDefinition]:
    definitions: list[ToolDefinition] = []
    for tool in tools or []:
        definition = _normalize_tool_definition(tool)
        if definition:
            definitions.append(definition)
    return definitions


def normalize_anthropic_tools(tools: list[dict[Any, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for tool in tools or []:
        tool_type = tool.get("type")
        if tool_type and tool_type not in {"custom", "function"}:
            normalized.append(dict(tool))
            continue
        definition = _normalize_tool_definition(tool)
        if definition:
            normalized.append(definition.to_anthropic())
    return normalized


def _normalize_tool_definition(tool: Mapping[Any, Any]) -> ToolDefinition | None:
    custom = tool.get("custom") if isinstance(tool.get("custom"), dict) else {}
    name = custom.get("name") or tool.get("name")
    if not name:
        return None

    input_schema = (
        custom.get("input_schema")
        or custom.get("inputSchema")
        or custom.get("parameters")
        or tool.get("input_schema")
        or tool.get("inputSchema")
        or tool.get("parameters")
        or DEFAULT_INPUT_SCHEMA
    )
    if not isinstance(input_schema, dict):
        input_schema = DEFAULT_INPUT_SCHEMA

    strict = tool.get("strict")
    return ToolDefinition(
        name=str(name),
        description=str(custom.get("description") or tool.get("description") or ""),
        input_schema=input_schema,
        strict=strict if isinstance(strict, bool) else None,
    )
