"""The shared provider-resolution step, and the lifecycle contract around it.

Both architectures used to carry their own copy of this block, and their own
copy of the try/except that turns a failure into an ERROR event. See
api/docs/LLD-agent-runtime-refactor.md (P1.7).
"""

from typing import AsyncIterator

import pytest

from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.agents.provider_session import ProviderNotConfigured, open_provider_session
from src.conversations.models import Conversation
from src.llm.events import SSEEvent, SSEEventType


def _agent(provider: str = "Anthropic", thinking: str | None = None) -> Agent:
    return Agent(
        agent_name="Test Agent",
        agent_architecture="krishna-memgpt",
        agent_provider=provider,
        agent_model="claude-sonnet-4",
        agent_persona="Helpful",
        agent_ollama_thinking=thinking,
        created_by="owner@example.com",
    )


class NoSettingsRepo:
    def find_by_provider(self, owner_email, provider_name):
        return None


class SettingsRepo:
    def find_by_provider(self, owner_email, provider_name):
        return object()


async def test_open_provider_session_raises_when_the_provider_is_not_configured():
    with pytest.raises(ProviderNotConfigured) as caught:
        await open_provider_session(
            _agent(provider="Bedrock"),
            owner_email="owner@example.com",
            provider_settings_repo=NoSettingsRepo(),
        )

    assert "Provider 'Bedrock' is not configured." in str(caught.value)
    assert "Settings > Provider Configuration" in str(caught.value)


async def test_open_provider_session_applies_the_thinking_override_only_for_ollama(monkeypatch):
    seen: list[dict] = []

    async def fake_load(**kwargs):
        return {"base": "creds"}

    def fake_merge(credentials, *, thinking_mode):
        seen.append({"thinking_mode": thinking_mode})
        return {**credentials, "think": thinking_mode}

    monkeypatch.setattr("src.agents.provider_session.load_provider_credentials", fake_load)
    monkeypatch.setattr("src.agents.provider_session.merge_thinking_override", fake_merge)
    monkeypatch.setattr("src.agents.provider_session.get_llm_provider", lambda name: name)

    ollama = await open_provider_session(
        _agent(provider="Ollama", thinking="enabled"),
        owner_email="owner@example.com",
        provider_settings_repo=SettingsRepo(),
    )
    anthropic = await open_provider_session(
        _agent(provider="Anthropic", thinking="enabled"),
        owner_email="owner@example.com",
        provider_settings_repo=SettingsRepo(),
    )

    assert ollama.credentials == {"base": "creds", "think": "enabled"}
    assert anthropic.credentials == {"base": "creds"}
    assert seen == [{"thinking_mode": "enabled"}]


class RaisingArchitecture(AgentArchitecture):
    async def _run_turn(self, **kwargs) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="u1")
        raise ProviderNotConfigured("Bedrock")

    @property
    def name(self) -> str:
        return "raising"


class QuietArchitecture(AgentArchitecture):
    async def _run_turn(self, **kwargs) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="hi")

    @property
    def name(self) -> str:
        return "quiet"


class ReportingArchitecture(AgentArchitecture):
    """Yields ERROR itself rather than raising, as the max-iterations path does."""

    async def _run_turn(self, **kwargs) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.ERROR, content="ran out of tool iterations")

    @property
    def name(self) -> str:
        return "reporting"


def _turn_args():
    agent = _agent()
    return {
        "agent": agent,
        "conversation": Conversation(
            title="c", agent_id=agent.agent_id, created_by="owner@example.com"
        ),
        "user_message": "hi",
        "owner_email": "owner@example.com",
        "actor_email": "owner@example.com",
        "actor_id": "owner@example.com",
    }


async def _events(architecture: AgentArchitecture) -> list[SSEEvent]:
    return [event async for event in architecture.handle_message(**_turn_args())]


async def test_a_raised_error_becomes_one_error_event_and_no_stream_complete():
    events = await _events(RaisingArchitecture())

    assert [e.event_type for e in events] == [
        SSEEventType.USER_MESSAGE_SAVED,
        SSEEventType.ERROR,
    ]
    assert "Provider 'Bedrock' is not configured." in events[-1].content


async def test_a_turn_that_did_not_fail_ends_with_stream_complete():
    events = await _events(QuietArchitecture())

    assert [e.event_type for e in events] == [
        SSEEventType.AGENT_RESPONSE_TO_USER,
        SSEEventType.STREAM_COMPLETE,
    ]


async def test_an_architecture_reported_error_also_suppresses_stream_complete():
    events = await _events(ReportingArchitecture())

    assert [e.event_type for e in events] == [SSEEventType.ERROR]


async def test_an_architecture_that_forgets_run_turn_says_so():
    class Incomplete(AgentArchitecture):
        @property
        def name(self) -> str:
            return "incomplete"

    events = await _events(Incomplete())

    assert events[0].event_type == SSEEventType.ERROR
    assert "must implement _run_turn" in events[0].content
