"""Factory helpers for default agent tool command registration."""

from __future__ import annotations

from src.agents.tool_runtime.commands import (
    ExecutorToolCommand,
    ToolExecutor,
    ToolSpec,
)
from src.agents.tool_runtime.executors import (
    MCPRuntime,
    MCPToolExecutor,
    NativeToolExecutor,
    NativeToolExecutorAdapter,
    SkillRuntime,
    SkillToolExecutor,
)
from src.agents.tool_runtime.mcp import MCP_TOOL_SPECS
from src.agents.tool_runtime.registry import ToolCommandRegistry
from src.agents.tool_runtime.skills import SKILL_TOOL_SPECS
from src.tools.native.specs import NATIVE_TOOL_SPECS


def build_default_tool_command_registry(
    *,
    skill_runtime: SkillRuntime,
    native_tools: NativeToolExecutor,
    mcp_runtime: MCPRuntime | None = None,
) -> ToolCommandRegistry:
    registry = ToolCommandRegistry()
    native_executor = NativeToolExecutorAdapter(native_tools)
    skill_executor = SkillToolExecutor(skill_runtime)
    mcp_executor = MCPToolExecutor(mcp_runtime)

    _register_specs(registry, NATIVE_TOOL_SPECS, native_executor)
    _register_specs(registry, SKILL_TOOL_SPECS, skill_executor)
    _register_specs(registry, MCP_TOOL_SPECS, mcp_executor)

    return registry


def _register_specs(
    registry: ToolCommandRegistry,
    specs: list[ToolSpec],
    executor: ToolExecutor,
) -> None:
    for spec in specs:
        registry.register(ExecutorToolCommand(spec=spec, executor=executor))
