"""Only an agent's owner links knowledge bases to it, and the agent only searches its owner's."""

from datetime import datetime, timedelta, timezone

import jwt

from src.agents.architectures.krishna_memgpt import KrishnaMemGPTArchitecture
from src.knowledge.models import KnowledgeBase
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from tests.mock_data import AGENT_CREATE_REQUEST, TEST_USER_EMAIL, TEST_USER_EMAIL_2


def _headers_for(email: str) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    token = jwt.encode({"aud": "owner", "sub": email, "iat": now, "exp": now + timedelta(hours=1)}, "test-secret")
    return {"Authorization": f"Bearer {token}"}


def _kb(owner: str) -> str:
    return KnowledgeBaseRepository().save(KnowledgeBase(name="KB", description="", created_by=owner)).kb_id


def test_nobody_else_can_link_list_or_unlink_on_your_agent(test_client, auth_headers):
    agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]
    own_kb = _kb(TEST_USER_EMAIL)
    attacker_kb = _kb(TEST_USER_EMAIL_2)
    attacker = _headers_for(TEST_USER_EMAIL_2)
    base = f"/agents/{agent_id}/knowledge-bases"

    assert test_client.post(f"{base}?kb_id={attacker_kb}", headers=attacker).status_code == 404
    assert test_client.post(f"{base}?kb_id={own_kb}", headers=auth_headers).status_code == 201
    assert test_client.get(base, headers=attacker).status_code == 404
    assert test_client.delete(f"{base}/{own_kb}", headers=attacker).status_code == 404
    assert [kb["kb_id"] for kb in test_client.get(base, headers=auth_headers).json()] == [own_kb]


def test_the_agent_never_searches_a_knowledge_base_its_owner_does_not_own(dynamodb_table):
    own_kb = _kb(TEST_USER_EMAIL)
    foreign_kb = _kb(TEST_USER_EMAIL_2)
    links = AgentKnowledgeBaseRepository()
    links.link("agent-1", own_kb, TEST_USER_EMAIL)
    links.link("agent-1", foreign_kb, TEST_USER_EMAIL_2)

    assert KrishnaMemGPTArchitecture()._get_linked_kb_ids("agent-1", TEST_USER_EMAIL) == [own_kb]
