"""Tool dispatch: the registry binds, the router sets policy.

The five-layer command/executor/adapter/resolver chain this replaced is
described in api/docs/LLD-agent-runtime-refactor.md (P1.3).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_runtime import (
    BoundTool,
    NativeToolContext,
    ToolCategory,
    ToolRegistry,
    ToolSpec,
    build_default_tool_registry,
)
from src.agents.tool_runtime.mcp import MCP_TOOL_SPECS
from src.agents.tool_runtime.skills import SKILL_TOOL_SPECS
from src.tools.native.specs import NATIVE_TOOL_SPECS


class FakeSkillRuntime:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def handle_tool_call(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return "skill result"


class FakeNativeTools:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self, tool_name: str, tool_input: dict[str, Any], context: NativeToolContext
    ) -> str:
        self.calls.append(
            {"tool_name": tool_name, "tool_input": tool_input, "context": context}
        )
        return "native result"


class FakeMCPRuntime:
    def __init__(self):
        self.list_calls: list[dict[str, Any]] = []
        self.call_calls: list[dict[str, Any]] = []

    async def list_runtime_tools(self, **kwargs) -> dict[str, Any]:
        self.list_calls.append(kwargs)
        return {"tools": []}

    async def call_runtime_tool(self, **kwargs) -> dict[str, Any]:
        self.call_calls.append(kwargs)
        return {"content": [{"text": "mcp result"}]}


def _state() -> AgentTurnState:
    return AgentTurnState(
        owner_email="owner@example.com",
        actor_email="actor@example.com",
        actor_id="actor-1",
        conversation_id="conversation-1",
        agent_id="agent-1",
        provider_name="OpenAI",
        model_name="gpt-5.5",
        user_message="hello",
        user_message_id="message-1",
    )


def _router(**overrides) -> tuple[ToolExecutionRouter, dict[str, Any]]:
    runtimes = {
        "skill_runtime": FakeSkillRuntime(),
        "native_tools": FakeNativeTools(),
        "mcp_runtime": FakeMCPRuntime(),
        **overrides,
    }
    return ToolExecutionRouter(build_default_tool_registry(**runtimes)), runtimes


# --- what the registry declares ------------------------------------------------


def test_every_declared_tool_validates_its_input():
    specs = [*NATIVE_TOOL_SPECS, *SKILL_TOOL_SPECS, *MCP_TOOL_SPECS]

    assert specs
    assert all(spec.input_model is not None for spec in specs)
    assert all(spec.name for spec in specs)


def test_only_core_memory_writes_are_declared_as_making_the_prompt_stale():
    stale = {spec.name for spec in NATIVE_TOOL_SPECS if spec.mutates_prompt_context}

    assert stale == {"core_memory_append", "core_memory_replace", "core_memory_delete"}


def test_definitions_are_offered_by_category():
    registry, _ = _router()

    native_only = registry._registry.definitions_for_categories({ToolCategory.NATIVE})
    with_skills = registry._registry.definitions_for_categories(
        {ToolCategory.NATIVE, ToolCategory.SKILL}
    )

    names = {d["name"] for d in native_only}
    assert "core_memory_append" in names
    assert "execute_skill_action" not in names
    assert "knowledge_base_search" not in names
    assert len(with_skills) > len(native_only)


def test_registering_the_same_tool_twice_is_refused():
    spec = ToolSpec({"name": "dup"}, ToolCategory.NATIVE)

    async def handler(tool_name, tool_input, state) -> str:
        return ""

    try:
        ToolRegistry([BoundTool(spec, handler), BoundTool(spec, handler)])
    except ValueError as exc:
        assert "dup" in str(exc)
    else:
        raise AssertionError("expected a duplicate registration to be refused")


# --- what the handlers receive -------------------------------------------------


async def test_a_skill_tool_reaches_the_skill_runtime_with_the_turn_identities():
    router, runtimes = _router()

    outcome = await router.execute(
        tool_name="execute_skill_action",
        tool_input={"skill_id": "demo", "action": "run", "arguments": {"q": "x"}},
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome == type(outcome)(result="skill result", success=True)
    [call] = runtimes["skill_runtime"].calls
    assert call["tool_name"] == "execute_skill_action"
    assert call["agent_id"] == "agent-1"
    assert call["owner_email"] == "owner@example.com"
    assert call["actor_email"] == "actor@example.com"
    assert call["actor_id"] == "actor-1"
    assert call["conversation_id"] == "conversation-1"
    assert call["user_message_id"] == "message-1"


async def test_a_native_tool_receives_a_context_built_from_the_turn_state():
    state = _state()
    state.linked_kb_ids = ["kb-1"]
    router, runtimes = _router()

    await router.execute(
        tool_name="core_memory_read",
        tool_input={"block": "human"},
        tool_use_id="tool-1",
        state=state,
    )

    [call] = runtimes["native_tools"].calls
    assert call["context"] == NativeToolContext(
        agent_id="agent-1",
        user_id="actor-1",
        conversation_id="conversation-1",
        linked_kb_ids=["kb-1"],
    )


async def test_mcp_tools_reach_their_own_handlers():
    router, runtimes = _router()
    state = _state()

    listed = await router.execute(
        tool_name="list_mcp_tools", tool_input={}, tool_use_id="t1", state=state
    )
    called = await router.execute(
        tool_name="call_mcp_tool",
        tool_input={"mcp_id": "atlassian", "tool_name": "search", "arguments": {"q": "x"}},
        tool_use_id="t2",
        state=state,
    )

    assert json.loads(listed.result) == {"tools": []}
    assert json.loads(called.result) == {"content": [{"text": "mcp result"}]}
    assert runtimes["mcp_runtime"].list_calls == [
        {"owner_email": "owner@example.com", "agent_id": "agent-1", "mcp_id": None}
    ]
    assert runtimes["mcp_runtime"].call_calls == [
        {
            "owner_email": "owner@example.com",
            "agent_id": "agent-1",
            "mcp_id": "atlassian",
            "tool_name": "search",
            "arguments": {"q": "x"},
        }
    ]


async def test_input_is_validated_before_the_handler_is_called():
    router, runtimes = _router()

    outcome = await router.execute(
        tool_name="call_mcp_tool",
        tool_input={"mcp_id": "atlassian"},  # missing tool_name and arguments
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome.success is False
    assert "Error" in outcome.result
    assert runtimes["mcp_runtime"].call_calls == []


async def test_an_absent_mcp_runtime_is_reported_not_crashed():
    router, _ = _router(mcp_runtime=None)

    outcome = await router.execute(
        tool_name="list_mcp_tools", tool_input={}, tool_use_id="tool-1", state=_state()
    )

    assert outcome.success is False
    assert "MCP runtime is not configured" in outcome.result


# --- router policy -------------------------------------------------------------


async def test_a_memory_write_marks_the_system_prompt_stale():
    state = _state()
    router, _ = _router()

    await router.execute(
        tool_name="core_memory_append",
        tool_input={"block": "human", "content": "Likes concise answers."},
        tool_use_id="tool-1",
        state=state,
    )

    assert state.prompt_dirty is True


async def test_a_memory_read_leaves_the_system_prompt_alone():
    state = _state()
    router, _ = _router()

    await router.execute(
        tool_name="core_memory_read",
        tool_input={"block": "human"},
        tool_use_id="tool-1",
        state=state,
    )

    assert state.prompt_dirty is False


async def test_a_memory_write_that_raises_does_not_mark_the_prompt_stale():
    class ExplodingNativeTools:
        async def execute(self, tool_name, tool_input, context) -> str:
            raise RuntimeError("write failed")

    state = _state()
    router, _ = _router(native_tools=ExplodingNativeTools())

    outcome = await router.execute(
        tool_name="core_memory_append",
        tool_input={"block": "human", "content": "x"},
        tool_use_id="tool-1",
        state=state,
    )

    assert outcome.success is False
    assert outcome.result == "Error: write failed"
    assert state.prompt_dirty is False


async def test_an_unknown_tool_is_a_result_the_model_can_read():
    router, _ = _router()

    outcome = await router.execute(
        tool_name="missing_tool", tool_input={}, tool_use_id="tool-1", state=_state()
    )

    assert outcome.success is False
    assert outcome.result == "Error: Unknown tool: missing_tool"


async def test_a_tool_that_outruns_its_timeout_reports_the_timeout():
    async def never_finishes(tool_name, tool_input, state) -> str:
        await asyncio.sleep(1)
        return "late"

    registry = ToolRegistry(
        [
            BoundTool(
                ToolSpec(
                    {"name": "slow_tool", "parameters": {"type": "object"}},
                    ToolCategory.NATIVE,
                    timeout_seconds=0.01,
                ),
                never_finishes,
            )
        ]
    )

    outcome = await ToolExecutionRouter(registry).execute(
        tool_name="slow_tool", tool_input={}, tool_use_id="tool-1", state=_state()
    )

    assert outcome.success is False
    assert "timed out" in outcome.result
