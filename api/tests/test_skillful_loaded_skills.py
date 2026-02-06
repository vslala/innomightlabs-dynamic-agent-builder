import json

from fastapi import status

from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL


def test_skillful_skills_load_persists_loaded_skills_block(test_client, auth_headers, dynamodb_table, monkeypatch):
    """End-to-end: krishna-skillful handles skills_load and writes to core memory loaded_skills."""

    # 1) Create agent with krishna-skillful
    create_req = dict(AGENT_CREATE_REQUEST)
    create_req["agent_architecture"] = "krishna-skillful"
    create_req["agent_provider"] = "Bedrock"

    agent_resp = test_client.post("/agents", json=create_req, headers=auth_headers)
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["agent_id"]

    # 2) Save provider settings for owner (required by architecture)
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

    # 3) Create conversation
    conv_resp = test_client.post(
        "/conversations/",
        json={"title": "t", "agent_id": agent_id},
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["conversation_id"]

    # 4) Patch LLM provider to request skills_load then respond with text
    class FakeLLMProvider:
        def __init__(self):
            self.calls = 0

        async def stream_response(self, messages, credentials, tools=None, model=None):
            from src.llm.providers.base import LLMEvent

            self.calls += 1
            if self.calls == 1:
                yield LLMEvent(
                    type="tool_use",
                    tool_use_id="tu_1",
                    tool_name="skills_load",
                    tool_input={"skill_id": "wordpress"},
                )
                yield LLMEvent(type="stop", content="tool")
            else:
                yield LLMEvent(type="text", content="done")
                yield LLMEvent(type="stop", content="end")

    fake = FakeLLMProvider()

    import src.agents.architectures.krishna_skillful as skillful_arch

    monkeypatch.setattr(skillful_arch, "get_llm_provider", lambda _name: fake)

    # 5) Send message via agent SSE endpoint and consume stream
    with test_client.stream(
        "POST",
        f"/agents/{agent_id}/{conversation_id}/send-message",
        json={"content": "hello"},
        headers=auth_headers,
    ) as resp:
        assert resp.status_code == 200
        # Consume some lines to force execution
        for _ in resp.iter_lines():
            pass

    # 6) Verify loaded_skills block created and contains wordpress record
    from src.memory.repository import MemoryRepository

    mem_repo = MemoryRepository()
    block_def = mem_repo.get_block_definition(agent_id, TEST_USER_EMAIL, "loaded_skills")
    assert block_def is not None
    assert getattr(block_def, "eviction_policy").value == "lru"

    core = mem_repo.get_core_memory(agent_id, TEST_USER_EMAIL, "loaded_skills")
    assert core is not None
    assert len(core.lines) >= 1

    # Find wordpress line
    objs = []
    for line in core.lines:
        try:
            objs.append(json.loads(line))
        except Exception:
            continue

    assert any(o.get("skill_id") == "wordpress" for o in objs)
