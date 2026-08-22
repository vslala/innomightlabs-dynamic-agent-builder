from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from src.agents.architectures.base import AgentInvocationResult
from src.llm.events import SSEEvent, SSEEventType
from tests.mock_data import AGENT_CREATE_REQUEST


class FakeA2AArchitecture:
    name = "fake-a2a"

    async def handle_message_buffered(self, **kwargs) -> AgentInvocationResult:
        return AgentInvocationResult(
            events=[
                SSEEvent(
                    event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
                    content=f"Echo: {kwargs['user_message']}",
                )
            ],
            response_text=f"Echo: {kwargs['user_message']}",
            success=True,
        )

    async def handle_message(self, **kwargs) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(
            event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
            content="Working",
        )
        yield SSEEvent(
            event_type=SSEEventType.AGENT_RESPONSE_TO_USER,
            content=f"Echo: {kwargs['user_message']}",
        )
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="Done")


def _create_enabled_agent_with_key(test_client: TestClient, auth_headers: dict) -> tuple[str, str]:
    agent_payload = {
        **AGENT_CREATE_REQUEST,
        "agent_name": "A2A Invocation Agent",
        "agent_description": "A2A invocation test agent",
    }
    agent_response = test_client.post("/agents", json=agent_payload, headers=auth_headers)
    assert agent_response.status_code == 201
    agent_id = agent_response.json()["agent_id"]

    key_response = test_client.post(
        f"/agents/{agent_id}/api-keys",
        json={"name": "A2A Test Key", "allowed_origins": []},
        headers=auth_headers,
    )
    assert key_response.status_code == 201
    api_key = key_response.json()["public_key"]

    sharing_response = test_client.put(
        f"/agents/{agent_id}/a2a-sharing",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert sharing_response.status_code == 200
    return agent_id, api_key


def _message_payload(*, text: str = "Hello", context_id: str | None = None) -> dict:
    message = {
        "messageId": "msg-test",
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if context_id:
        message["contextId"] = context_id
    return {
        "message": message,
        "configuration": {"acceptedOutputModes": ["text/plain"]},
    }


def test_message_send_requires_agent_api_key(test_client: TestClient, auth_headers: dict):
    agent_id, _api_key = _create_enabled_agent_with_key(test_client, auth_headers)

    response = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_message_send_invokes_existing_architecture_and_persists_task(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)

    response = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(text="Plan the launch"),
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/a2a+json")
    task = response.json()["task"]
    assert task["agentId"] == agent_id
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["status"]["message"]["parts"][0]["text"] == "Echo: Plan the launch"
    assert task["conversationId"].startswith(f"a2a-{agent_id}-")

    lookup_response = test_client.get(
        f"/a2a/agents/{agent_id}/tasks/{task['id']}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert lookup_response.status_code == 200
    assert lookup_response.json()["task"]["id"] == task["id"]


def test_jsonrpc_message_send_invokes_existing_architecture(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)

    response = test_client.post(
        f"/a2a/agents/{agent_id}",
        json={
            "jsonrpc": "2.0",
            "id": "rpc-test",
            "method": "SendMessage",
            "params": _message_payload(text="Use JSON-RPC"),
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == "rpc-test"
    task = payload["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert task["status"]["message"]["parts"][0]["text"] == "Echo: Use JSON-RPC"


def test_jsonrpc_tasks_get_returns_persisted_task(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)
    headers = {"Authorization": f"Bearer {api_key}"}
    send_response = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(text="Persist me"),
        headers=headers,
    )
    task_id = send_response.json()["task"]["id"]

    response = test_client.post(
        f"/a2a/agents/{agent_id}",
        json={
            "jsonrpc": "2.0",
            "id": "task-get",
            "method": "GetTask",
            "params": {"id": task_id},
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["id"] == task_id


def test_context_id_reuses_internal_conversation(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)
    headers = {"Authorization": f"Bearer {api_key}"}

    first = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(text="First", context_id="ctx-shared"),
        headers=headers,
    )
    second = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(text="Second", context_id="ctx-shared"),
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task"]["contextId"] == "ctx-shared"
    assert second.json()["task"]["contextId"] == "ctx-shared"
    assert first.json()["task"]["conversationId"] == second.json()["task"]["conversationId"]


def test_task_lookup_is_scoped_to_authenticated_api_key(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)
    second_key_response = test_client.post(
        f"/agents/{agent_id}/api-keys",
        json={"name": "Other A2A Test Key", "allowed_origins": []},
        headers=auth_headers,
    )
    assert second_key_response.status_code == 201
    second_api_key = second_key_response.json()["public_key"]

    send_response = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    task_id = send_response.json()["task"]["id"]

    lookup_response = test_client.get(
        f"/a2a/agents/{agent_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {second_api_key}"},
    )

    assert lookup_response.status_code == 404


def test_dashboard_owner_can_list_and_get_agent_a2a_tasks(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)
    send_response = test_client.post(
        f"/a2a/agents/{agent_id}/message:send",
        json=_message_payload(text="Dashboard visible task"),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert send_response.status_code == 200
    task_id = send_response.json()["task"]["id"]

    list_response = test_client.get(
        f"/agents/{agent_id}/a2a-tasks",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    task_ids = {task["id"] for task in list_response.json()["items"]}
    assert task_id in task_ids

    get_response = test_client.get(
        f"/agents/{agent_id}/a2a-tasks/{task_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["task"]["id"] == task_id


def test_message_stream_emits_a2a_task_status_events(
    test_client: TestClient,
    auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "src.a2a.service.get_agent_architecture",
        lambda _architecture: FakeA2AArchitecture(),
    )
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)

    response = test_client.post(
        f"/a2a/agents/{agent_id}/message:stream",
        json=_message_payload(text="Stream this"),
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert "TASK_STATE_WORKING" in response.text
    assert "TASK_STATE_COMPLETED" in response.text
    assert "Echo: Stream this" in response.text


def test_cancel_returns_unsupported_operation(
    test_client: TestClient,
    auth_headers: dict,
):
    agent_id, api_key = _create_enabled_agent_with_key(test_client, auth_headers)

    response = test_client.post(
        f"/a2a/agents/{agent_id}/tasks/task-123:cancel",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 501
    assert response.json()["code"] == "UNSUPPORTED_OPERATION"
