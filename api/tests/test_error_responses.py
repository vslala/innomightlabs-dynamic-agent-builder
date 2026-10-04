"""Clients get a generic message and a request id; the details stay in the logs."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.agents.provider_session import ProviderNotConfigured
from src.common.pagination import InvalidCursor, decode_cursor
from src.conversations.models import Conversation
from src.exceptions import GENERIC_ERROR_MESSAGE, register_exception_handlers
from src.llm.events import SSEEventType
from src.middleware.request_id import RequestIdMiddleware
from src.skills.models import ActorKind


def _app() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("ValidationException: table innomight-prod key schema mismatch")

    @app.get("/page")
    async def page(cursor: str):
        decode_cursor(cursor)
        return {}

    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_error_hides_its_text_and_names_the_request():
    response = _app().get("/boom", headers={"X-Request-Id": "req-123"})

    assert response.status_code == 500
    assert response.json() == {"detail": GENERIC_ERROR_MESSAGE, "request_id": "req-123", "path": "/boom"}
    assert "innomight-prod" not in response.text


def _cursor(value) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


@pytest.mark.parametrize(
    "cursor",
    ["not-base64!", _cursor([1, 2]), _cursor({"pk": "a"}), _cursor({"pk": "a", "sk": 1}), _cursor({"pk": "a", "sk": "b", "x": "c"})],
)
def test_a_malformed_cursor_is_a_400(cursor: str):
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor)
    assert _app().get("/page", params={"cursor": cursor}).status_code == 400


def test_a_cursor_we_issued_round_trips():
    assert decode_cursor(_cursor({"pk": "Conversation#1", "sk": "Message#2"})) == {
        "pk": "Conversation#1",
        "sk": "Message#2",
    }


class _Failing(AgentArchitecture):
    def __init__(self, error: Exception):
        self.error = error

    @property
    def name(self) -> str:
        return "failing"

    async def _run_turn(self, **kwargs):
        raise self.error
        yield  # pragma: no cover


async def _error_for(error: Exception, actor_kind: ActorKind) -> str:
    agent = Agent(agent_name="a", agent_architecture="krishna-mini", agent_provider="Bedrock", agent_persona="p", created_by="o")
    events = [
        event
        async for event in _Failing(error).handle_message(
            agent=agent,
            conversation=Conversation(title="c", agent_id=agent.agent_id, created_by="o"),
            user_message="hi",
            owner_email="o",
            actor_email="v",
            actor_id="v",
            actor_kind=actor_kind,
        )
    ]
    assert [event.event_type for event in events] == [SSEEventType.ERROR]
    return events[0].content


@pytest.mark.asyncio
async def test_a_failed_turn_tells_visitors_and_api_callers_nothing_internal():
    internal = RuntimeError("botocore ClientError: AccessDenied on arn:aws:dynamodb:...")

    for kind in (ActorKind.VISITOR, ActorKind.API, ActorKind.A2A):
        assert await _error_for(internal, kind) == GENERIC_ERROR_MESSAGE
    assert "AccessDenied" in await _error_for(internal, ActorKind.OWNER)


@pytest.mark.asyncio
async def test_an_error_written_for_users_is_shown_to_everyone():
    message = await _error_for(ProviderNotConfigured("Anthropic"), ActorKind.VISITOR)

    assert "Anthropic" in message
