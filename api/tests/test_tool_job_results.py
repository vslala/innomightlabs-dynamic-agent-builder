"""KAN-67: a large async tool result is kept whole, and in a chat Invoke Agent hands back only the answer, filing
the invoked agent's full tool history in S3 under the tool call's id for audit."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import boto3
import pytest
from botocore.exceptions import ClientError

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.agents.tool_execution import ToolExecutionRouter, current_tool_call_id
from src.agents.tool_runtime import BoundTool, ToolCategory, ToolRegistry, ToolSpec
from src.agents.tool_runtime.jobs import ToolJob, ToolJobRepository, ToolJobStatus
from src.agents.tool_runtime.jobs.repository import INLINE_RESULT_MAX_BYTES
from src.agents.tool_runtime.jobs.service import ToolJobService
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from src.skills.agent_invocation import actions as invoke_actions
from src.skills.agent_invocation.history import InvocationHistoryStore, key_for
from tests.mock_data import TEST_USER_EMAIL

#: Bigger than a DynamoDB item may be (400 KB), like a researcher's dozen searches.
LARGE = {"response_text": "x" * 450_000}


@pytest.fixture
def bucket(dynamodb_table):
    boto3.client("s3", region_name=settings.conversation_media_region).create_bucket(
        Bucket=settings.conversation_media_bucket,
        **({} if settings.conversation_media_region == "us-east-1" else {
            "CreateBucketConfiguration": {"LocationConstraint": settings.conversation_media_region}
        }),
    )


def running_job() -> ToolJob:
    repository = ToolJobRepository()
    job = repository.create(ToolJob(
        owner_email=TEST_USER_EMAIL, actor_email=TEST_USER_EMAIL, actor_id=TEST_USER_EMAIL,
        agent_id="agent-1", conversation_id="conv-1", tool_name="execute_skill_action",
        skill_id="agent_invocation", installed_skill_id="agent_invocation", action="invoke",
    ))
    repository.mark_running(job.job_id, "Running invoke...")
    return job


def raw_item(job: ToolJob) -> dict:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(settings.dynamodb_table)
    return table.get_item(Key={"pk": job.pk, "sk": job.sk})["Item"]


def status(job: ToolJob) -> dict:
    return ToolJobService(repository=ToolJobRepository()).check_job_for_agent(
        job_id=job.job_id, owner_email=TEST_USER_EMAIL, actor_email=TEST_USER_EMAIL,
        agent_id="agent-1", conversation_id="conv-1",
    )


def test_the_item_limit_is_real(dynamodb_table):
    """What failed before: storing a result this size on the job's item."""
    job = running_job()
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(settings.dynamodb_table)
    with pytest.raises(ClientError, match="size"):
        table.update_item(
            Key={"pk": job.pk, "sk": job.sk},
            UpdateExpression="SET #result = :result",
            ExpressionAttributeNames={"#result": "result"},
            ExpressionAttributeValues={":result": LARGE},
        )


def test_a_normal_result_stays_on_the_job(bucket):
    job = running_job()
    ToolJobRepository().mark_succeeded(job.job_id, {"response_text": "short"})
    item = raw_item(job)
    assert item["result"] == {"response_text": "short"} and item.get("result_ref") is None
    assert status(job)["result"] == {"response_text": "short"}


def test_a_large_result_is_kept_whole_in_s3(bucket):
    job = running_job()
    saved = ToolJobRepository().mark_succeeded(job.job_id, LARGE)

    assert saved.status == ToolJobStatus.SUCCEEDED
    item = raw_item(job)
    assert item.get("result") is None and item["result_ref"].endswith(f"/tool-jobs/{job.job_id}/result.json")
    assert TEST_USER_EMAIL not in item["result_ref"]  # owner-scoped by hash, never by email
    payload = status(job)
    assert payload["ok"] is True and payload["result"] == LARGE  # nothing lost or truncated


def test_the_threshold_leaves_room_for_the_rest_of_the_item():
    assert INLINE_RESULT_MAX_BYTES <= 300_000


# --- Invoke Agent ------------------------------------------------------------------------------


class FakeArchitecture:
    async def handle_message_buffered(self, **kwargs):
        searches = [
            SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content="result " * 3000, tool_name="tavily_search")
            for _ in range(30)
        ]
        return SimpleNamespace(
            success=True, error=None, response_text="Findings with sources.", events=searches,
            user_message_id="u1", assistant_message_id="a1",
        )


@pytest.fixture
def invoke_setup(dynamodb_table, monkeypatch):
    monkeypatch.setattr(invoke_actions, "get_agent_architecture", lambda *args, **kwargs: FakeArchitecture())
    agent = AgentRepository().save(Agent(
        agent_name="Researcher", agent_architecture="krishna-memgpt", agent_provider="Bedrock",
        agent_persona="Research.", created_by=TEST_USER_EMAIL,
    ))
    conversation = ConversationRepository().save(
        Conversation(title="Lead", agent_id="lead", created_by=TEST_USER_EMAIL)
    )
    context = {"owner_email": TEST_USER_EMAIL, "conversation_id": conversation.conversation_id}
    return agent, context


async def test_a_chat_agent_gets_only_the_answer_and_the_history_is_filed_by_tool_call(invoke_setup, bucket):
    agent, context = invoke_setup
    result = await invoke_actions.invoke(
        {"prompt_template": "Research X"}, {"target_agent_id": agent.agent_id}, {**context, "tool_call_id": "toolu_42"}
    )

    # Nothing but the answer in the caller's context: the history is found from its audit record's tool_call_id.
    assert result == {
        "response_text": "Findings with sources.",
        "message_ids": {"user_message_id": "u1", "assistant_message_id": "a1"},
    }
    key = key_for(TEST_USER_EMAIL, context["conversation_id"], "toolu_42")
    assert key.endswith("/tool_audit_toolu_42.json") and TEST_USER_EMAIL not in key
    history = InvocationHistoryStore().load(key)
    assert history["tool_call_id"] == "toolu_42" and history["prompt"] == "Research X"
    assert history["invoked_agent_id"] == agent.agent_id and len(history["tool_calls"]) == 30
    assert history["tool_calls"][0]["content"] == "result " * 3000  # whole, not capped like the run log


async def test_losing_the_audit_copy_never_costs_the_answer(invoke_setup):
    agent, context = invoke_setup  # no bucket, so saving the history fails
    result = await invoke_actions.invoke(
        {"prompt_template": "Research X"}, {"target_agent_id": agent.agent_id}, {**context, "tool_call_id": "toolu_1"}
    )
    assert result["response_text"] == "Findings with sources."


async def test_each_concurrent_tool_call_sees_its_own_id():
    seen: dict[str, str | None] = {}

    async def handler(tool_name, tool_input, state):
        await asyncio.sleep(0)  # let the other call run in between
        seen[tool_input["name"]] = current_tool_call_id.get()
        return "ok"

    spec = ToolSpec({"name": "probe", "description": "", "parameters": {"type": "object"}}, ToolCategory.BUILDER)
    router = ToolExecutionRouter(ToolRegistry([BoundTool(spec, handler)]))
    await asyncio.gather(
        router.execute(tool_name="probe", tool_input={"name": "a"}, tool_use_id="toolu_a", state=None),
        router.execute(tool_name="probe", tool_input={"name": "b"}, tool_use_id="toolu_b", state=None),
    )
    assert seen == {"a": "toolu_a", "b": "toolu_b"}
    assert current_tool_call_id.get() is None  # reset after each call


async def test_an_automation_still_gets_the_tool_calls_for_its_inspector(invoke_setup):
    agent, context = invoke_setup
    result = await invoke_actions.invoke(
        {"prompt_template": "Research X", "agent_id": agent.agent_id},
        {},
        {**context, "orchestrator_type": "automation"},
    )
    assert len(result["events"]) == 30

