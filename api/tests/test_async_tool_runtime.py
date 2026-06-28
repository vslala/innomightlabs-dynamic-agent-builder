from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.agents.agentic_loop import AsyncToolJobStillRunningError, run_agentic_tool_loop
from src.agents.tool_execution import ToolExecutionOutcome
from src.agents.tool_runtime.jobs import ToolJob, ToolJobRepository, ToolJobStatus
from src.agents.tool_runtime.jobs.service import ToolJobService
from src.skills.service import SkillRuntimeService
from src.tools.native.handlers import NativeToolHandler

from tests.mock_data import TEST_USER_EMAIL
from tests.test_skills import _create_agent_for_user


@dataclass
class FakeProviderEvent:
    type: str
    content: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] | None = None
    tool_use_id: str = ""


class AsyncStartProvider:
    def __init__(self):
        self.contexts: list[list[dict[Any, Any]]] = []
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        self.contexts.append(list(context))
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="execute_skill_action",
                tool_input={"skill_id": "demo", "action": "run", "arguments": {}, "async": True},
                tool_use_id="tooluse_1",
            )
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="I will wait and check again.")
        yield FakeProviderEvent(type="stop")


class AsyncStartRouter:
    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        if tool_name == "wait":
            return ToolExecutionOutcome(
                result=json.dumps({"ok": True, "waited_seconds": 20, "message": "Wait complete."}),
                success=True,
            )
        if tool_name == "check_tool_job":
            return ToolExecutionOutcome(
                result=json.dumps(
                    {
                        "ok": True,
                        "async": True,
                        "job_id": tool_input["job_id"],
                        "status": "succeeded",
                        "result": {"ok": True},
                    }
                ),
                success=True,
            )
        return ToolExecutionOutcome(
            result=json.dumps(
                {
                    "ok": True,
                    "async": True,
                    "job_id": "tooljob_test",
                    "status": "queued",
                    "check_tool": "check_tool_job",
                    "wait_tool": "wait",
                }
            ),
            success=True,
        )


class AsyncWaitThenFinishProvider:
    def __init__(self):
        self.contexts: list[list[dict[Any, Any]]] = []
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        self.contexts.append(list(context))
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="execute_skill_action",
                tool_input={"skill_id": "demo", "action": "run", "arguments": {}, "async": True},
                tool_use_id="tooluse_start",
            )
            yield FakeProviderEvent(type="stop")
            return
        if self.calls == 2:
            yield FakeProviderEvent(type="text", content="Report generation is running - I'll check shortly.")
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="wait",
                tool_input={"seconds": 5, "reason": "waiting for async job"},
                tool_use_id="tooluse_wait",
            )
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="The job is still running.")
        yield FakeProviderEvent(type="stop")


class AsyncWaitRouter:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        self.calls.append({"tool_name": tool_name, "tool_input": tool_input, "tool_use_id": tool_use_id})
        if tool_name == "execute_skill_action":
            return ToolExecutionOutcome(
                result=json.dumps(
                    {
                        "ok": True,
                        "async": True,
                        "job_id": "tooljob_wait_case",
                        "status": "queued",
                    }
                ),
                success=True,
            )
        if tool_name == "wait":
            return ToolExecutionOutcome(
                result=json.dumps({"ok": True, "waited_seconds": 5, "message": "Wait complete."}),
                success=True,
            )
        if tool_name == "check_tool_job":
            return ToolExecutionOutcome(
                result=json.dumps(
                    {
                        "ok": True,
                        "async": True,
                        "job_id": tool_input["job_id"],
                        "status": "succeeded",
                        "result": {"ok": True, "done": True},
                    }
                ),
                success=True,
            )
        raise AssertionError(f"Unexpected tool {tool_name}")


class AlwaysRunningAsyncRouter:
    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        if tool_name == "execute_skill_action":
            return ToolExecutionOutcome(
                result=json.dumps(
                    {
                        "ok": True,
                        "async": True,
                        "job_id": "tooljob_always_running",
                        "status": "queued",
                    }
                ),
                success=True,
            )
        if tool_name == "wait":
            return ToolExecutionOutcome(
                result=json.dumps({"ok": True, "waited_seconds": 20, "message": "Wait complete."}),
                success=True,
            )
        if tool_name == "check_tool_job":
            return ToolExecutionOutcome(
                result=json.dumps(
                    {
                        "ok": True,
                        "async": True,
                        "job_id": tool_input["job_id"],
                        "status": "running",
                    }
                ),
                success=True,
            )
        raise AssertionError(f"Unexpected tool {tool_name}")


def test_tool_job_repository_persists_status_and_ttl(dynamodb_table):
    repo = ToolJobRepository()
    job = repo.create(
        ToolJob(
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            agent_id="agent-1",
            conversation_id="conversation-1",
            tool_name="execute_skill_action",
            skill_id="demo",
            installed_skill_id="demo",
            action="run",
            arguments={"score": 1.5},
            context={"owner_email": TEST_USER_EMAIL},
        )
    )

    assert job.ttl > 0
    assert repo.find_by_id(job.job_id).status == ToolJobStatus.QUEUED

    running = repo.mark_running(job.job_id, "Working...")
    assert running.status == ToolJobStatus.RUNNING
    assert running.progress_message == "Working..."

    succeeded = repo.mark_succeeded(job.job_id, {"ok": True, "value": 2.5})
    assert succeeded.status == ToolJobStatus.SUCCEEDED
    assert succeeded.to_status_payload()["result"] == {"ok": True, "value": 2.5}


def test_tool_job_service_fails_stale_running_job(dynamodb_table):
    repo = ToolJobRepository()
    service = ToolJobService(repository=repo)
    job = repo.create(
        ToolJob(
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            agent_id="agent-1",
            conversation_id="conversation-1",
            tool_name="execute_skill_action",
            skill_id="demo",
            installed_skill_id="demo",
            action="run",
            arguments={},
            context={},
            status=ToolJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        )
    )

    payload = service.check_job_for_agent(
        job_id=job.job_id,
        owner_email=TEST_USER_EMAIL,
        actor_email=TEST_USER_EMAIL,
        agent_id="agent-1",
        conversation_id="conversation-1",
    )

    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert "stale" in payload["error"]


def test_skill_runtime_starts_async_job_without_storing_decrypted_config(
    dynamodb_table,
    monkeypatch,
):
    agent = _create_agent_for_user(TEST_USER_EMAIL)
    runtime = SkillRuntimeService()
    runtime.repository.upsert_with_config(
        agent_id=agent.agent_id,
        installed_skill_id="league_insights_report",
        skill_id="league_insights_report",
        namespace="games.league_of_legends",
        skill_name="League Insights Report",
        skill_description="Generate reports",
        enabled=True,
        installed_by=TEST_USER_EMAIL,
        plain_config={"report_agent_id": agent.agent_id, "default_routing_region": "europe"},
        secret_config={"riot_api_key": "RGAPI-secret"},
        secret_fields=["riot_api_key"],
    )
    started_jobs: list[str] = []

    def fake_start(job):
        started_jobs.append(job.job_id)

    monkeypatch.setattr(runtime.tool_job_service, "start_skill_action_job", fake_start)

    result = asyncio.run(
        runtime.handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "league_insights_report",
                "action": "generate_match_report",
                "arguments": {"game_name": "Demon Simon", "tag_line": "messi"},
                "async": True,
            },
            agent_id=agent.agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id="conv-test",
        )
    )

    payload = json.loads(result)
    assert payload["async"] is True
    assert payload["status"] == "queued"
    assert payload["wait_tool"] == "wait"
    assert started_jobs == [payload["job_id"]]

    raw = dynamodb_table.get_item(
        Key={"pk": f"User#{TEST_USER_EMAIL}", "sk": f"ToolJob#{payload['job_id']}"}
    )["Item"]
    assert "RGAPI-secret" not in json.dumps(raw, default=str)
    assert "config" not in raw


async def test_wait_tool_defaults_clamps_and_uses_sleep(monkeypatch):
    sleeps: list[int] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("src.tools.native.handlers.asyncio.sleep", fake_sleep)

    handler = NativeToolHandler(memory_repo=object(), message_repo=object())
    default_result = json.loads(await handler.execute("wait", {}, "agent-1"))
    clamped_result = json.loads(await handler.execute("wait", {"seconds": 999}, "agent-1"))

    assert default_result["waited_seconds"] == 20
    assert clamped_result["waited_seconds"] == 600
    assert sleeps == [20, 600]


async def test_agentic_loop_injects_async_job_followup_instruction():
    provider = AsyncStartProvider()
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=AsyncStartRouter(),
            state=object(),
        )
    ]

    second_context = provider.contexts[1]
    synthetic = second_context[-1]["content"][0]["text"]

    assert "Do not finish the conversation" in synthetic
    assert "wait" in synthetic
    assert "check_tool_job" in synthetic
    assert "tooljob_test" in synthetic
    assert any(event.kind == "complete" for event in events)


async def test_agentic_loop_auto_checks_async_job_after_wait():
    provider = AsyncWaitThenFinishProvider()
    router = AsyncWaitRouter()
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=router,
            state=object(),
        )
    ]

    assert [call["tool_name"] for call in router.calls] == [
        "execute_skill_action",
        "wait",
        "check_tool_job",
    ]
    assert router.calls[-1]["tool_input"] == {"job_id": "tooljob_wait_case"}
    assert any(
        event.kind == "tool_call_start" and event.payload["tool_name"] == "check_tool_job"
        for event in events
    )
    third_context = provider.contexts[2]
    assert any(
        item.get("role") == "user"
        and "succeeded" in json.dumps(item)
        for item in third_context
    )
    assert any(event.kind == "complete" for event in events)


async def test_async_job_self_check_ignores_normal_iteration_limit(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.MAX_TOOL_ITERATIONS", 1)
    provider = AsyncWaitThenFinishProvider()
    router = AsyncWaitRouter()

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=router,
            state=object(),
        )
    ]

    assert [call["tool_name"] for call in router.calls] == [
        "execute_skill_action",
        "wait",
        "check_tool_job",
    ]
    assert provider.calls == 3
    assert any(event.kind == "complete" for event in events)


async def test_agentic_loop_does_not_complete_while_async_job_is_active(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS", 0)
    provider = AsyncWaitThenFinishProvider()
    events = []

    with pytest.raises(AsyncToolJobStillRunningError):
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=AlwaysRunningAsyncRouter(),
            state=object(),
        ):
            events.append(event)

    assert any(event.kind == "tool_call_result" for event in events)
    assert not any(event.kind == "complete" for event in events)
