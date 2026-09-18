from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.dream.models import DreamRun, DreamRunStatus
from src.dream.repository import DreamRepository
from src.dream.service import get_dream_service
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2


def _headers_for(email: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": email,
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _save_agent(repository: AgentRepository, *, owner_email: str, agent_id: str) -> Agent:
    agent = Agent(
        agent_id=agent_id,
        agent_name="Dream agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_persona="Maintain core memory.",
        created_by=owner_email,
    )
    return repository.save(agent)


def test_settings_are_user_scoped_and_invalid_cron_is_rejected(
    test_client: TestClient, auth_headers: dict[str, str]
):
    assert test_client.get("/dream/settings", headers=auth_headers).json() is None

    invalid = test_client.put(
        "/dream/settings",
        headers=auth_headers,
        json={"enabled": False, "cron_expression": "not a cron", "timezone": "UTC"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Cron expression must use 5 fields: minute hour day month weekday"

    saved = test_client.put(
        "/dream/settings",
        headers=auth_headers,
        json={"enabled": False, "cron_expression": "15 2 * * *", "timezone": "UTC"},
    )

    assert saved.status_code == 200
    assert saved.json()["user_email"] == TEST_USER_EMAIL
    assert saved.json()["cron_expression"] == "15 2 * * *"
    assert test_client.get("/dream/settings", headers=_headers_for(TEST_USER_EMAIL_2)).json() is None


def test_run_history_is_scoped_to_the_owned_agent_and_user(
    test_client: TestClient, auth_headers: dict[str, str], dynamodb_table
):
    agent_repository = AgentRepository()
    own_agent = _save_agent(agent_repository, owner_email=TEST_USER_EMAIL, agent_id="own-dream-agent")
    foreign_agent = _save_agent(agent_repository, owner_email=TEST_USER_EMAIL_2, agent_id="foreign-dream-agent")
    dream_repository = DreamRepository()
    dream_repository.save_run(DreamRun(
        run_id="own-run",
        agent_id=own_agent.agent_id,
        user_id=TEST_USER_EMAIL,
        owner_email=TEST_USER_EMAIL,
        status=DreamRunStatus.SUCCEEDED,
    ))
    dream_repository.save_run(DreamRun(
        run_id="other-user-run",
        agent_id=own_agent.agent_id,
        user_id=TEST_USER_EMAIL_2,
        owner_email=TEST_USER_EMAIL_2,
        status=DreamRunStatus.SUCCEEDED,
    ))

    response = test_client.get(f"/agents/{own_agent.agent_id}/dream/runs?limit=0", headers=auth_headers)
    assert response.status_code == 200
    assert [run["run_id"] for run in response.json()] == ["own-run"]

    foreign = test_client.get(f"/agents/{foreign_agent.agent_id}/dream/runs", headers=auth_headers)
    assert foreign.status_code == 404
    assert foreign.json()["detail"] == "Agent not found"


def test_manual_run_accepts_only_an_owned_agent(
    test_client: TestClient, auth_headers: dict[str, str], dynamodb_table, monkeypatch
):
    agent_repository = AgentRepository()
    own_agent = _save_agent(agent_repository, owner_email=TEST_USER_EMAIL, agent_id="own-dream-agent")
    foreign_agent = _save_agent(agent_repository, owner_email=TEST_USER_EMAIL_2, agent_id="foreign-dream-agent")

    class FakeDreamService:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        async def dream(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    service = FakeDreamService()
    monkeypatch.setitem(test_client.app.dependency_overrides, get_dream_service, lambda: service)

    foreign = test_client.post(f"/agents/{foreign_agent.agent_id}/dream/run", headers=auth_headers)
    assert foreign.status_code == 404
    assert service.calls == []

    accepted = test_client.post(f"/agents/{own_agent.agent_id}/dream/run", headers=auth_headers)
    assert accepted.status_code == 202
    assert accepted.json() == {"status": "accepted"}
    assert service.calls == [{
        "agent_id": own_agent.agent_id,
        "user_id": TEST_USER_EMAIL,
        "owner_email": TEST_USER_EMAIL,
        "mode": "manual",
    }]
