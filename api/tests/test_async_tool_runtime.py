from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.agents.agentic_loop import (
    AsyncToolJobStillRunningError,
    TurnComplete,
    run_agentic_tool_loop,
)
from src.agents.tool_execution import ToolExecutionOutcome
from src.llm.events import SSEEventType
from src.agents.tool_runtime.contexts import NativeToolContext
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


class RecordingAsyncRouter:
    """Starts an async job, then reports `statuses` on successive polls.

    The last status is repeated if the loop polls more times than there are
    entries, so a "never finishes" router is just `["running"] * n`.
    """

    def __init__(
        self,
        *,
        statuses: list[str],
        progress_message: str | None = None,
        synchronous_result: str | None = None,
    ):
        self.statuses = statuses
        self.progress_message = progress_message
        self.synchronous_result = synchronous_result
        self.calls: list[dict[str, Any]] = []
        self._polls = 0

    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        self.calls.append(
            {"tool_name": tool_name, "tool_input": tool_input, "tool_use_id": tool_use_id}
        )

        if tool_name == "check_tool_job":
            index = min(self._polls, len(self.statuses) - 1)
            self._polls += 1
            payload = {
                "ok": True,
                "async": True,
                "job_id": tool_input["job_id"],
                "status": self.statuses[index],
            }
            if self.progress_message:
                payload["progress_message"] = self.progress_message
            return ToolExecutionOutcome(result=json.dumps(payload), success=True)

        if self.synchronous_result is not None:
            return ToolExecutionOutcome(result=self.synchronous_result, success=True)

        return ToolExecutionOutcome(
            result=json.dumps(
                {"ok": True, "async": True, "job_id": "tooljob_test", "status": "queued"}
            ),
            success=True,
        )


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
    context = NativeToolContext(
        agent_id="agent-1",
        user_id="user-1",
        conversation_id="conversation-1",
        linked_kb_ids=[],
    )
    default_result = json.loads(await handler.execute("wait", {}, context))
    clamped_result = json.loads(await handler.execute("wait", {"seconds": 999}, context))

    assert default_result["waited_seconds"] == 20
    assert clamped_result["waited_seconds"] == 600
    assert sleeps == [20, 600]


async def test_the_loop_settles_an_async_job_itself_and_shows_only_the_real_tool_call(
    monkeypatch,
):
    """The model asks for one tool and sees one terminal result.

    It used to be driven through a synthetic wait/check cycle, which cost extra
    LLM round trips and put tool calls the user never caused into the
    timeline. See api/docs/LLD-agent-runtime-refactor.md (P1.2).
    """
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_JOB_POLL_SECONDS", 0)
    provider = AsyncStartProvider()
    router = RecordingAsyncRouter(statuses=["running", "succeeded"])

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

    # The loop polled check_tool_job; the model was never asked to.
    assert [call["tool_name"] for call in router.calls] == [
        "execute_skill_action",
        "check_tool_job",
        "check_tool_job",
    ]

    started = [e for e in events if getattr(e, "event_type", None) == SSEEventType.TOOL_CALL_START]
    results = [e for e in events if getattr(e, "event_type", None) == SSEEventType.TOOL_CALL_RESULT]
    assert [e.tool_name for e in started] == ["execute_skill_action"]
    assert [e.tool_name for e in results] == ["execute_skill_action"]

    # The result the model receives is the job's terminal payload, not "queued".
    assert json.loads(results[0].content)["status"] == "succeeded"
    assert any(isinstance(event, TurnComplete) for event in events)

    # One follow-up call after the tool settled, not one per poll.
    assert provider.calls == 2


async def test_waiting_on_a_job_reports_progress_to_the_client(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_JOB_POLL_SECONDS", 0)
    router = RecordingAsyncRouter(
        statuses=["running", "running", "succeeded"],
        progress_message="Rendering page 2 of 9...",
    )

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=AsyncStartProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=router,
            state=object(),
        )
    ]

    notices = [
        event.content
        for event in events
        if getattr(event, "event_type", None) == SSEEventType.LIFECYCLE_NOTIFICATION
    ]
    assert notices == ["Rendering page 2 of 9...", "Rendering page 2 of 9..."]


async def test_the_turn_fails_if_a_job_outlives_the_in_turn_budget(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_JOB_POLL_SECONDS", 0)
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS", 0)
    events = []

    with pytest.raises(AsyncToolJobStillRunningError):
        async for event in run_agentic_tool_loop(
            provider=AsyncStartProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=RecordingAsyncRouter(statuses=["running"] * 50),
            state=object(),
        ):
            events.append(event)

    # No tool result is reported, because there is no honest one to report.
    assert not any(
        getattr(e, "event_type", None) == SSEEventType.TOOL_CALL_RESULT for e in events
    )
    assert not any(isinstance(event, TurnComplete) for event in events)


async def test_a_synchronous_tool_result_is_passed_straight_through(monkeypatch):
    """A result with no async job must not be polled or altered."""
    monkeypatch.setattr("src.agents.agentic_loop.ASYNC_JOB_POLL_SECONDS", 0)
    router = RecordingAsyncRouter(statuses=[], synchronous_result="done immediately")

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=AsyncStartProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=router,
            state=object(),
        )
    ]

    assert [call["tool_name"] for call in router.calls] == ["execute_skill_action"]
    results = [e for e in events if getattr(e, "event_type", None) == SSEEventType.TOOL_CALL_RESULT]
    assert results[0].content == "done immediately"

async def test_start_skill_action_job_keeps_a_strong_reference_while_running():
    """Regression: asyncio only weakly references a running task, so a bare
    create_task(...) whose result nobody keeps can be collected mid-execution.
    See api/docs/LLD-agent-runtime-refactor.md (P0.2).
    """
    import asyncio

    from src.agents.tool_runtime.jobs import service as jobs_service

    started = asyncio.Event()
    release = asyncio.Event()

    class SlowService(jobs_service.ToolJobService):
        def __init__(self):
            pass

        async def execute_skill_action_job(self, job_id: str) -> None:
            started.set()
            await release.wait()

    job = ToolJob(
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
        tool_name="execute_skill_action",
    )

    jobs_service._running_jobs.clear()
    SlowService().start_skill_action_job(job)
    await started.wait()

    assert len(jobs_service._running_jobs) == 1

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert jobs_service._running_jobs == set()
