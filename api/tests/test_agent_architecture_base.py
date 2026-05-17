from typing import AsyncIterator

from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.conversations.models import Conversation
from src.llm.events import SSEEvent, SSEEventType


class FakeArchitecture(AgentArchitecture):
    async def handle_message(
        self,
        agent: Agent,
        conversation: Conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments=None,
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="User message saved",
            message_id="user-message-1",
        )
        yield SSEEvent(
            event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
            content="hello ",
        )
        yield SSEEvent(
            event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
            content="world",
        )
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id="assistant-message-1",
        )
        yield SSEEvent(
            event_type=SSEEventType.STREAM_COMPLETE,
            content="Response complete",
        )

    @property
    def name(self) -> str:
        return "fake"


async def test_handle_message_buffered_extracts_common_invocation_fields():
    architecture = FakeArchitecture()
    agent = Agent(
        agent_name="Test Agent",
        agent_architecture="fake",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by="owner@example.com",
    )
    conversation = Conversation(
        title="Test Conversation",
        agent_id=agent.agent_id,
        created_by="owner@example.com",
    )

    result = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message="Say hello",
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
    )

    assert result.success is True
    assert result.error is None
    assert result.user_message_id == "user-message-1"
    assert result.assistant_message_id == "assistant-message-1"
    assert result.response_text == "hello world"
    assert [event.event_type for event in result.events] == [
        SSEEventType.USER_MESSAGE_SAVED,
        SSEEventType.AGENT_RESPONSE_TO_USER,
        SSEEventType.AGENT_RESPONSE_TO_USER,
        SSEEventType.ASSISTANT_MESSAGE_SAVED,
        SSEEventType.STREAM_COMPLETE,
    ]


class FailingArchitecture(AgentArchitecture):
    async def handle_message(
        self,
        agent: Agent,
        conversation: Conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments=None,
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(
            event_type=SSEEventType.ERROR,
            content="Provider is not configured",
        )

    @property
    def name(self) -> str:
        return "failing"


async def test_handle_message_buffered_marks_error_events_as_failed():
    architecture = FailingArchitecture()
    agent = Agent(
        agent_name="Test Agent",
        agent_architecture="failing",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by="owner@example.com",
    )
    conversation = Conversation(
        title="Test Conversation",
        agent_id=agent.agent_id,
        created_by="owner@example.com",
    )

    result = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message="Say hello",
        owner_email="owner@example.com",
        actor_email="owner@example.com",
        actor_id="owner@example.com",
    )

    assert result.success is False
    assert result.error == "Provider is not configured"
    assert result.response_text == ""
