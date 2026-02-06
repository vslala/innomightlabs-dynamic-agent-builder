import json

from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL


def test_switching_architecture_to_skillful_creates_loaded_skills_block(test_client, auth_headers, dynamodb_table, monkeypatch):
    """If an agent is updated from memgpt->skillful, loaded_skills block should be created on first run."""

    # Create agent as krishna-memgpt
    create_req = dict(AGENT_CREATE_REQUEST)
    create_req["agent_architecture"] = "krishna-memgpt"
    create_req["agent_provider"] = "Bedrock"

    agent_resp = test_client.post("/agents", json=create_req, headers=auth_headers)
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["agent_id"]

    # Update architecture to krishna-skillful
    update_resp = test_client.put(
        f"/agents/{agent_id}",
        json={
            "agent_architecture": "krishna-skillful",
        },
        headers=auth_headers,
    )
    assert update_resp.status_code == 200

    # Provider settings for owner (required by skillful)
    from src.settings.models import ProviderSettings
    from src.settings.repository import ProviderSettingsRepository
    from src.crypto import encrypt

    repo = ProviderSettingsRepository()
    creds = {"access_key": "x", "secret_key": "y"}
    ps = ProviderSettings(
        user_email=TEST_USER_EMAIL,
        provider_name="Bedrock",
        encrypted_credentials=encrypt(json.dumps(creds)),
    )
    repo.save(ps)

    # Create conversation
    conv_resp = test_client.post(
        "/conversations/",
        json={"title": "t", "agent_id": agent_id},
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["conversation_id"]

    # Fake LLM provider to avoid hitting Bedrock
    class FakeLLMProvider:
        async def stream_response(self, messages, credentials, tools=None, model=None):
            from src.llm.providers.base import LLMEvent
            yield LLMEvent(type="text", content="ok")
            yield LLMEvent(type="stop", content="end")

    import src.agents.architectures.krishna_skillful as skillful_arch

    monkeypatch.setattr(skillful_arch, "get_llm_provider", lambda _name: FakeLLMProvider())

    # Run one message through SSE endpoint (this triggers init)
    with test_client.stream(
        "POST",
        f"/agents/{agent_id}/{conversation_id}/send-message",
        json={"content": "hello"},
        headers=auth_headers,
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass

    # Verify block exists
    from src.memory.repository import MemoryRepository

    mem_repo = MemoryRepository()
    assert mem_repo.get_block_definition(agent_id, TEST_USER_EMAIL, "loaded_skills") is not None
    assert mem_repo.get_core_memory(agent_id, TEST_USER_EMAIL, "loaded_skills") is not None
