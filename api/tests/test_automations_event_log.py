"""An agent step's tool calls are kept whole in S3, and the run inspector reads them back in order."""

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import boto3
import pytest

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.event_log import StepEventLogStore, events_holder, inline_events
from src.automations.models import AutomationRunNodeResult
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.config import settings
from src.conversations.repository import ConversationRepository
from src.llm.events import MAX_RECORDED_EVENT_CONTENT_CHARS, RECORDED_CONTENT_TRUNCATION_MARKER, SSEEvent, SSEEventType
from tests.mock_data import TEST_USER_EMAIL, agent_fields
from tests.mock_data import test_owner as _test_owner
from tests.test_automations_runner import SuccessfulArchitecture, build_graph

TEST_OWNER = _test_owner()
LONG_PAGE = "p" * (MAX_RECORDED_EVENT_CONTENT_CHARS + 1_000)
T0 = datetime(2026, 11, 9, 9, 0, 0, tzinfo=timezone.utc)


class ToolCallingArchitecture(SuccessfulArchitecture):
    """The model asks for both tools at once, then they run one after another."""

    async def handle_message(self, *args, **kwargs) -> AsyncIterator[SSEEvent]:  # type: ignore[override]
        for tool_call_id, url in (("tc_1", "https://a.example"), ("tc_2", "https://b.example")):
            yield SSEEvent(
                event_type=SSEEventType.TOOL_CALL_START,
                content="Calling fetch_page...",
                tool_call_id=tool_call_id,
                tool_name="fetch_page",
                tool_args={"url": url},
            )
        for second, tool_call_id in ((1, "tc_1"), (3, "tc_2")):
            yield SSEEvent(
                event_type=SSEEventType.TOOL_CALL_RESULT,
                content=LONG_PAGE,
                tool_call_id=tool_call_id,
                tool_name="fetch_page",
                success=True,
                started_at=T0.replace(second=second),
                completed_at=T0.replace(second=second + 1),
            )
        async for event in super().handle_message(*args, **kwargs):
            yield event


class UnavailableStore(StepEventLogStore):
    def save(self, *args, **kwargs) -> Optional[str]:  # type: ignore[override]
        return None


@pytest.fixture
def media_bucket(dynamodb_table):
    boto3.client("s3", region_name=settings.conversation_media_region).create_bucket(
        Bucket=settings.conversation_media_bucket
    )


@pytest.fixture
def agent(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Researcher",
        agent_architecture="tools",
        agent_provider="Bedrock",
        agent_persona="Curious",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    monkeypatch.setattr("src.automations.runner.get_agent_architecture", lambda _: ToolCallingArchitecture())
    return agent


async def run_draft_step(agent: Agent, event_logs: StepEventLogStore | None = None) -> AutomationRunNodeResult:
    repo = AutomationRepository()
    graph = build_graph(agent.agent_id)
    repo.save_automation(graph.automation)
    runner = AutomationRunner(
        automation_repo=repo,
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
        event_logs=event_logs,
    )
    run = await runner.run_test(graph, None, {"name": "Ada"}, TEST_OWNER)
    return next(result for result in repo.find_node_results(run.run_id) if result.node_id == "draft")


async def test_runner_keeps_the_whole_log_in_s3_and_out_of_the_items(agent, media_bucket):
    draft = await run_draft_step(agent)

    assert draft.event_log_key and draft.event_log_key.endswith(f"/automation-runs/{draft.run_id}/{draft.result_id}.json")
    assert draft.tool_call_count == 2
    assert "events" not in draft.output
    assert draft.output["response_text"] == "Echo: Hello Ada"
    run = AutomationRepository().find_run_by_id(draft.run_id)
    assert run and "events" not in run.context["nodes"]["draft"]["output"]

    events = StepEventLogStore().load(draft.event_log_key)
    assert [(event["event_type"], event["tool_call_id"]) for event in events] == [
        ("TOOL_CALL_START", "tc_1"),
        ("TOOL_CALL_START", "tc_2"),
        ("TOOL_CALL_RESULT", "tc_1"),
        ("TOOL_CALL_RESULT", "tc_2"),
    ]
    assert events[2]["content"] == LONG_PAGE, "the log is never truncated"
    assert events[3]["started_at"] == "2026-11-09T09:00:03Z"


async def test_runner_keeps_a_capped_copy_inline_when_s3_is_unavailable(agent):
    draft = await run_draft_step(agent, event_logs=UnavailableStore())

    assert draft.event_log_key is None
    assert draft.tool_call_count == 2
    result = draft.output["events"][2]
    assert result["content"].endswith(RECORDED_CONTENT_TRUNCATION_MARKER)


def test_events_holder_finds_an_agent_step_and_an_invoke_agent_skill_action():
    agent_step = {"response_text": "hi", "events": [{"event_type": "TOOL_CALL_START"}]}
    skill_action = {"action": "invoke", "result": {"response_text": "hi", "events": []}}

    assert events_holder(agent_step) is agent_step
    assert events_holder(skill_action) is skill_action["result"]
    assert events_holder({"result": "plain"}) is None
    assert inline_events({"result": {"items": []}}) == []


def test_a_result_saved_before_event_logs_counts_its_inline_tool_calls(dynamodb_table):
    repo = AutomationRepository()
    legacy = AutomationRunNodeResult(
        run_id="run-1",
        automation_id="auto-1",
        node_id="draft",
        output={"events": [{"event_type": "TOOL_CALL_START"}, {"event_type": "TOOL_CALL_RESULT"}]},
    )
    item = legacy.to_dynamo_item()
    del item["tool_call_count"], item["event_log_key"]
    repo.table.put_item(Item=item)

    (loaded,) = repo.find_node_results("run-1")
    assert loaded.tool_call_count == 1
    assert loaded.event_log_key is None


async def test_step_events_route_serves_the_log_then_inline_events(agent, media_bucket, test_client, auth_headers):
    draft = await run_draft_step(agent)
    url = f"/automations/{draft.automation_id}/runs/{draft.run_id}/results/{draft.result_id}/events"

    response = test_client.get(url, headers=auth_headers)
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 4
    assert events[3]["content"] == LONG_PAGE

    run_detail = test_client.get(f"/automations/{draft.automation_id}/runs/{draft.run_id}", headers=auth_headers)
    (step,) = [item for item in run_detail.json()["node_results"] if item["node_id"] == "draft"]
    assert step["tool_call_count"] == 2
    assert "event_log_key" not in step, "the S3 key stays server-side"


async def test_step_events_route_rejects_an_unknown_result(agent, media_bucket, test_client, auth_headers):
    draft = await run_draft_step(agent)

    response = test_client.get(
        f"/automations/{draft.automation_id}/runs/{draft.run_id}/results/missing/events", headers=auth_headers
    )
    assert response.status_code == 404
