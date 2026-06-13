"""Registry for agent tool commands."""

from __future__ import annotations

from typing import Any, Iterable

from src.agents.tool_runtime.commands import ToolCommand


class ToolCommandRegistry:
    def __init__(self, commands: Iterable[ToolCommand] | None = None):
        self._commands: dict[str, ToolCommand] = {}
        for command in commands or []:
            self.register(command)

    def register(self, command: ToolCommand) -> None:
        if command.name in self._commands:
            raise ValueError(f"Tool command already registered: {command.name}")
        self._commands[command.name] = command

    def get(self, tool_name: str) -> ToolCommand:
        command = self._commands.get(tool_name)
        if not command:
            raise ValueError(f"Unknown tool: {tool_name}")
        return command

    def definitions(self) -> list[dict[str, Any]]:
        return [command.definition for command in self._commands.values()]
