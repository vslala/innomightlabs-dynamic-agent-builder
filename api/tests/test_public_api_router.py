"""
Tests for the public /v1 API authenticated with agent secret keys.
"""

import json
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import ActorKind
from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL


class _RecordingArchitecture:
    """Completes a turn in a handful of events and remembers how it was invoked."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle_message(self, **kwargs):
        self.calls.append(kwargs)
        yield SSEEvent(event_type=SSEEventType.LIFECYCLE_NOTIFICATION, content="Thinking...")
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.AGENT_THOUGHTS, content="internal reasoning")
        yield SSEEvent(
            event_type=SSEEventType.TOOL_CALL_START,
            content="",
            tool_call_id="call-1",
            tool_name="call_mcp_tool",
            display_tool_name="search_docs",
            tool_args={"secret": "internal"},
        )
        yield SSEEvent(event_type=SSEEventType.TOOL_CALL_RESULT, content="", tool_call_id="call-1", success=True)
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="Hello ")
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="there")
        yield SSEEvent(event_type=SSEEventType.TOKEN_USAGE_UPDATE, content="", total_tokens=999)
        yield SSEEvent(event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED, content="saved", message_id="assistant-1")
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")


class _FailingArchitecture:
    async def handle_message(self, **kwargs):
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.ERROR, content="the model provider is unavailable")


@pytest.fixture
def architecture(monkeypatch) -> _RecordingArchitecture:
    fake = _RecordingArchitecture()
    monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: fake)
    return fake


def _create_agent(test_client: TestClient, auth_headers: dict, name: str = "Support Agent") -> str:
    response = test_client.post("/agents", json={**AGENT_CREATE_REQUEST, "agent_name": name}, headers=auth_headers)
    return cast(str, response.json()["agent_id"])


def _create_key(test_client: TestClient, auth_headers: dict, agent_id: str) -> dict:
    response = test_client.post(f"/agents/{agent_id}/secret-keys", json={"name": "Server"}, headers=auth_headers)
    return cast(dict, response.json())


def _bearer(key: dict) -> dict:
    return {"Authorization": f"Bearer {key['secret']}"}


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


@pytest.fixture
def api(test_client: TestClient, auth_headers: dict):
    """An agent with one secret key, plus helpers to call /v1 with it."""
    agent_id = _create_agent(test_client, auth_headers)
    key = _create_key(test_client, auth_headers, agent_id)

    class Api:
        def __init__(self) -> None:
            self.agent_id = agent_id
            self.key = key
            self.headers = _bearer(key)
            self.base = f"/v1/agents/{agent_id}"

        def create_conversation(self, **body) -> dict:
            response = test_client.post(f"{self.base}/conversations", json=body, headers=self.headers)
            assert response.status_code == 201
            return cast(dict, response.json())

    return Api()


class TestAuthentication:
    def test_missing_key_is_401(self, test_client: TestClient, api):
        assert test_client.get(api.base).status_code == 401

    def test_non_secret_bearer_is_401(self, test_client: TestClient, api, auth_headers: dict):
        """A dashboard JWT is not an API key."""
        assert test_client.get(api.base, headers=auth_headers).status_code == 401

    def test_unknown_key_is_401(self, test_client: TestClient, api):
        response = test_client.get(api.base, headers={"Authorization": "Bearer sk_live_not-a-real-key"})

        assert response.status_code == 401

    def test_disabled_key_is_401(self, test_client: TestClient, api, auth_headers: dict):
        test_client.patch(
            f"/agents/{api.agent_id}/secret-keys/{api.key['key_id']}", json={"is_active": False}, headers=auth_headers
        )

        assert test_client.get(api.base, headers=api.headers).status_code == 401

    def test_a_deactivated_owners_keys_stop_working(self, test_client: TestClient, api):
        from src.users import UserRepository
        from tests.mock_data import TEST_USER_EMAIL

        UserRepository().mark_inactive(TEST_USER_EMAIL)

        assert test_client.get(api.base, headers=api.headers).status_code == 401

    def test_key_for_another_agent_is_403(self, test_client: TestClient, api):
        response = test_client.get("/v1/agents/some-other-agent", headers=api.headers)

        assert response.status_code == 403

    def test_each_call_counts_a_request(self, test_client: TestClient, api, auth_headers: dict):
        test_client.get(api.base, headers=api.headers)
        test_client.get(api.base, headers=api.headers)

        key = test_client.get(f"/agents/{api.agent_id}/secret-keys/{api.key['key_id']}", headers=auth_headers).json()
        assert key["request_count"] == 2
        assert key["last_used_at"] is not None


class TestAgentAndConversations:
    def test_get_agent(self, test_client: TestClient, api):
        response = test_client.get(api.base, headers=api.headers)

        assert response.status_code == 200
        assert response.json()["agent_id"] == api.agent_id
        assert response.json()["name"] == "Support Agent"

    def test_create_and_get_conversation(self, test_client: TestClient, api):
        created = api.create_conversation(title="Order help", end_user_id="customer-42")

        fetched = test_client.get(
            f"{api.base}/conversations/{created['conversation_id']}",
            params={"end_user_id": "customer-42"},
            headers=api.headers,
        )

        assert fetched.status_code == 200
        assert fetched.json() == created
        assert created["title"] == "Order help"
        assert created["end_user_id"] == "customer-42"

    def test_conversation_title_defaults_to_agent_name(self, api):
        assert api.create_conversation()["title"] == "Chat with Support Agent"

    def test_list_conversations_is_scoped_to_the_key(self, test_client: TestClient, api, auth_headers: dict):
        mine = api.create_conversation()
        other_key = _create_key(test_client, auth_headers, api.agent_id)
        test_client.post(f"{api.base}/conversations", json={}, headers=_bearer(other_key))

        listed = test_client.get(f"{api.base}/conversations", headers=api.headers).json()

        assert [item["conversation_id"] for item in listed["items"]] == [mine["conversation_id"]]
        assert listed["has_more"] is False

    def test_other_keys_cannot_read_a_conversation(self, test_client: TestClient, api, auth_headers: dict):
        conversation = api.create_conversation()
        other_key = _create_key(test_client, auth_headers, api.agent_id)

        response = test_client.get(
            f"{api.base}/conversations/{conversation['conversation_id']}", headers=_bearer(other_key)
        )

        assert response.status_code == 404

    def test_dashboard_conversations_are_not_reachable(self, test_client: TestClient, api, auth_headers: dict):
        dashboard = test_client.post(
            "/conversations/", json={"title": "Mine", "agent_id": api.agent_id}, headers=auth_headers
        ).json()

        response = test_client.get(f"{api.base}/conversations/{dashboard['conversation_id']}", headers=api.headers)

        assert response.status_code == 404

    def test_api_conversations_stay_out_of_the_dashboard_list(self, test_client: TestClient, api, auth_headers: dict):
        api.create_conversation()

        dashboard = test_client.get("/conversations/", headers=auth_headers).json()

        assert dashboard["items"] == []


class TestEndUserPartitions:
    """Each end user's conversations live in their own partition within the key."""

    def _list(self, test_client: TestClient, api, end_user_id: str | None = None) -> list[str]:
        params = {"end_user_id": end_user_id} if end_user_id else {}
        listed = test_client.get(f"{api.base}/conversations", params=params, headers=api.headers).json()
        return [item["conversation_id"] for item in listed["items"]]

    def test_each_end_user_lists_only_their_own_conversations(self, test_client: TestClient, api):
        alice = api.create_conversation(end_user_id="alice@example.com")
        bob = api.create_conversation(end_user_id="bob@example.com")
        keys_own = api.create_conversation()

        assert self._list(test_client, api, "alice@example.com") == [alice["conversation_id"]]
        assert self._list(test_client, api, "bob@example.com") == [bob["conversation_id"]]
        assert self._list(test_client, api) == [keys_own["conversation_id"]]

    @pytest.mark.parametrize("asked_as", [None, "bob@example.com"])
    def test_a_conversation_is_only_found_under_its_own_end_user(self, test_client: TestClient, api, asked_as):
        conversation = api.create_conversation(end_user_id="alice@example.com", context="Alice's brief")
        path = f"{api.base}/conversations/{conversation['conversation_id']}"
        params = {"end_user_id": asked_as} if asked_as else {}

        responses = [
            test_client.get(path, params=params, headers=api.headers),
            test_client.get(f"{path}/messages", params=params, headers=api.headers),
            test_client.patch(path, params=params, json={"context": "hijacked"}, headers=api.headers),
            test_client.post(f"{path}/messages", params=params, json={"content": "Hi", "stream": False}, headers=api.headers),
        ]
        fetched = test_client.get(path, params={"end_user_id": "alice@example.com"}, headers=api.headers).json()

        assert [response.status_code for response in responses] == [404, 404, 404, 404]
        assert fetched["context"] == "Alice's brief"

    def test_the_same_end_user_id_under_another_key_is_another_partition(
        self, test_client: TestClient, api, auth_headers: dict
    ):
        api.create_conversation(end_user_id="alice@example.com")
        other_key = _create_key(test_client, auth_headers, api.agent_id)

        listed = test_client.get(
            f"{api.base}/conversations", params={"end_user_id": "alice@example.com"}, headers=_bearer(other_key)
        ).json()

        assert listed["items"] == []


class TestConversationContext:
    BRIEF = "The user is bidding on tender T-881 for road resurfacing in Leeds."

    def _patch(self, test_client: TestClient, api, conversation_id: str, body: dict, headers: dict | None = None):
        return test_client.patch(
            f"{api.base}/conversations/{conversation_id}", json=body, headers=headers or api.headers
        )

    def test_a_conversation_starts_with_its_context(self, test_client: TestClient, api):
        conversation = api.create_conversation(context=self.BRIEF)

        fetched = test_client.get(f"{api.base}/conversations/{conversation['conversation_id']}", headers=api.headers)

        assert conversation["context"] == self.BRIEF
        assert fetched.json()["context"] == self.BRIEF

    def test_a_conversation_has_no_context_unless_given_one(self, api):
        assert api.create_conversation()["context"] is None

    def test_patch_replaces_the_context_and_keeps_everything_else(self, test_client: TestClient, api):
        conversation = api.create_conversation(title="Tender chat", end_user_id="customer-42", context="old")
        path = f"{api.base}/conversations/{conversation['conversation_id']}"
        end_user = {"end_user_id": "customer-42"}

        response = test_client.patch(path, params=end_user, json={"context": self.BRIEF}, headers=api.headers)
        fetched = test_client.get(path, params=end_user, headers=api.headers).json()

        assert response.status_code == 200
        assert response.json()["context"] == self.BRIEF
        assert fetched["context"] == self.BRIEF
        assert (fetched["title"], fetched["end_user_id"]) == ("Tender chat", "customer-42")
        assert fetched["updated_at"] is not None

    def test_a_long_context_is_accepted(self, test_client: TestClient, api):
        conversation = api.create_conversation()
        brief = "x" * 100_000

        response = self._patch(test_client, api, conversation["conversation_id"], {"context": brief})

        assert response.json()["context"] == brief

    @pytest.mark.parametrize("body", [{}, {"context": None}])
    def test_an_empty_patch_changes_nothing(self, test_client: TestClient, api, body: dict):
        conversation = api.create_conversation(title="Tender chat", context=self.BRIEF)

        response = self._patch(test_client, api, conversation["conversation_id"], body)
        fetched = test_client.get(
            f"{api.base}/conversations/{conversation['conversation_id']}", headers=api.headers
        ).json()

        assert response.status_code == 200
        assert fetched == conversation

    def test_other_keys_cannot_change_a_conversations_context(self, test_client: TestClient, api, auth_headers: dict):
        conversation = api.create_conversation(context=self.BRIEF)
        other_key = _create_key(test_client, auth_headers, api.agent_id)

        response = self._patch(
            test_client, api, conversation["conversation_id"], {"context": "hijacked"}, headers=_bearer(other_key)
        )
        fetched = test_client.get(
            f"{api.base}/conversations/{conversation['conversation_id']}", headers=api.headers
        ).json()

        assert response.status_code == 404
        assert fetched["context"] == self.BRIEF

    def test_patching_an_unknown_conversation_is_404(self, test_client: TestClient, api):
        assert self._patch(test_client, api, "missing", {"context": self.BRIEF}).status_code == 404

    def test_every_turn_runs_with_the_latest_context(self, test_client: TestClient, api, architecture):
        conversation = api.create_conversation(context="old")
        self._patch(test_client, api, conversation["conversation_id"], {"context": self.BRIEF})

        test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hello", "stream": False},
            headers=api.headers,
        )

        assert architecture.calls[0]["conversation"].context == self.BRIEF


class TestSendMessage:
    def test_stream_emits_only_public_events(self, test_client: TestClient, api, architecture):
        conversation = api.create_conversation()

        response = test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hi"},
            headers=api.headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers.get("X-Turn-Id")
        assert _sse_events(response.text) == [
            ("message.created", {"message_id": "user-1", "role": "user"}),
            ("tool.started", {"tool_call_id": "call-1", "name": "search_docs"}),
            ("tool.completed", {"tool_call_id": "call-1", "success": True}),
            ("message.delta", {"text": "Hello "}),
            ("message.delta", {"text": "there"}),
            ("message.completed", {"message_id": "assistant-1", "role": "assistant"}),
            ("done", {}),
        ]

    def test_buffered_reply(self, test_client: TestClient, api, architecture):
        conversation = api.create_conversation()

        response = test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hi", "stream": False},
            headers=api.headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "Hello there"
        assert body["user_message_id"] == "user-1"
        assert body["assistant_message_id"] == "assistant-1"
        assert body["conversation_id"] == conversation["conversation_id"]
        assert body["turn_id"]

    def test_buffered_failure_is_500(self, test_client: TestClient, api, monkeypatch):
        monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: _FailingArchitecture())
        conversation = api.create_conversation()

        response = test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hi", "stream": False},
            headers=api.headers,
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "the model provider is unavailable"

    def test_runs_as_owner_with_key_scoped_memory(self, test_client: TestClient, api, architecture):
        conversation = api.create_conversation()

        test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hi", "stream": False},
            headers=api.headers,
        )

        call = architecture.calls[0]
        assert call["owner_email"] == TEST_USER_EMAIL
        assert call["actor_email"] == TEST_USER_EMAIL
        assert call["actor_id"] == f"secret-key:{api.key['key_id']}"
        assert call["api_key_id"] == api.key["key_id"]
        assert call["user_message"] == "Hi"

    def test_end_user_gets_their_own_memory_scope(self, test_client: TestClient, api, architecture):
        conversation = api.create_conversation(end_user_id="customer-42")

        test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            params={"end_user_id": "customer-42"},
            json={"content": "Hi", "stream": False},
            headers=api.headers,
        )

        assert architecture.calls[0]["actor_id"] == f"secret-key:{api.key['key_id']}:customer-42"
        assert architecture.calls[0]["actor_kind"] == ActorKind.API

    def test_conflicts_with_running_turn(self, test_client: TestClient, api):
        from src.agents.turns import ConversationTurnRepository
        from src.agents.turns.models import ConversationTurn

        conversation = api.create_conversation()
        active = ConversationTurn(
            conversation_id=conversation["conversation_id"], agent_id=api.agent_id, created_by=TEST_USER_EMAIL
        )
        ConversationTurnRepository().create(active)

        response = test_client.post(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Hi"},
            headers=api.headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["turn_id"] == active.turn_id

    def test_unknown_conversation_is_404(self, test_client: TestClient, api, architecture):
        response = test_client.post(
            f"{api.base}/conversations/does-not-exist/messages", json={"content": "Hi"}, headers=api.headers
        )

        assert response.status_code == 404
        assert architecture.calls == []

    def test_list_messages_newest_first(self, test_client: TestClient, api):
        from src.messages.models import Message
        from src.messages.repositories.factory import get_message_repository

        conversation = api.create_conversation()
        repo = get_message_repository()
        for role, content in [("user", "Hi"), ("system", "tool audit"), ("assistant", "Hello")]:
            repo.save(
                Message(
                    conversation_id=conversation["conversation_id"],
                    created_by=TEST_USER_EMAIL,
                    role=role,
                    content=content,
                )
            )

        response = test_client.get(
            f"{api.base}/conversations/{conversation['conversation_id']}/messages", headers=api.headers
        )

        assert response.status_code == 200
        assert [(m["role"], m["content"]) for m in response.json()["items"]] == [
            ("assistant", "Hello"),
            ("user", "Hi"),
        ]


class TestKeyUsage:
    def test_usage_endpoint_reads_the_keys_partition(self, test_client: TestClient, api, auth_headers: dict):
        from src.token_usage.service import TokenUsageService

        TokenUsageService().record_usage(
            owner_email=TEST_USER_EMAIL,
            agent_id=api.agent_id,
            llm_model="model-a",
            prompt_tokens=10,
            completion_tokens=5,
            api_key_id=api.key["key_id"],
        )
        TokenUsageService().record_usage(
            owner_email=TEST_USER_EMAIL,
            agent_id=api.agent_id,
            llm_model="model-a",
            prompt_tokens=100,
            completion_tokens=50,
        )

        response = test_client.get(
            f"/agents/{api.agent_id}/secret-keys/{api.key['key_id']}/usage",
            params={"period": "month"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        series = response.json()["series"]
        assert len(series) == 1
        assert series[0]["total_tokens"] == 15

    def test_usage_for_unknown_key_is_404(self, test_client: TestClient, api, auth_headers: dict):
        response = test_client.get(
            f"/agents/{api.agent_id}/secret-keys/missing/usage", params={"period": "month"}, headers=auth_headers
        )

        assert response.status_code == 404
