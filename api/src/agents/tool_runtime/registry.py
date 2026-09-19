"""The tools available to an agent this turn, by name."""

from __future__ import annotations

from typing import Any, Iterable

from src.agents.tool_runtime.specs import BoundTool, ToolCategory


class ToolRegistry:
    def __init__(self, tools: Iterable[BoundTool] = ()):
        self._tools: dict[str, BoundTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: BoundTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> BoundTool:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")
        return tool

    def specs(self) -> list[Any]:
        return [tool.spec for tool in self._tools.values()]

    def definitions_for_categories(self, categories: set[ToolCategory]) -> list[dict[str, Any]]:
        """Only the tools the model should be told about this turn."""
        return [
            tool.spec.definition
            for tool in self._tools.values()
            if tool.spec.category in categories
        ]
