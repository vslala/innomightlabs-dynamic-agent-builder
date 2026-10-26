"""Deciding a consent card over HTTP, and the owner's "always allow" settings. See docs/LLD-action-consent.md."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.consent.models import ConsentRequest, ConsentStatus, SkillActionSubject, skill_key
from src.consent.preview import ConsentPreview
from src.consent.repository import ConsentRepository
from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import AgentSkill
from src.skills.repository import AgentSkillRepository
from tests.mock_data import (
    AGENT_CREATE_REQUEST,
    CONVERSATION_CREATE_REQUEST,
    TEST_USER_EMAIL,
    TEST_USER_EMAIL_2,
    account_for,
    user_id_for,
)


class _RecordingArchitecture:
    def __init__(self):
        self.turns: list[dict[str, Any]] = []

    async def handle_message(self, **kwargs):
        self.turns.append(kwargs)
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")


def _headers_for(email: str) -> dict[str, str]:
    from datetime import datetime, timedelta, timezone

    import jwt

    now = datetime.now(timezone.utc)
    token = jwt.encode({"aud": "owner", "sub": user_id_for(email), "iat": now, "exp": now + timedelta(hours=1)}, "test-secret")
    return {"Authorization": f"Bearer {token}"}


def _chat(test_client: TestClient, auth_headers: dict) -> tuple[str, str]:
    agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]
    conversation_id = test_client.post(
        "/conversations/", json={**CONVERSATION_CREATE_REQUEST, "agent_id": agent_id}, headers=auth_headers
    ).json()["conversation_id"]
    return agent_id, str(conversation_id)


def _pending(agent_id: str, conversation_id: str) -> ConsentRequest:
    return ConsentRepository().open(
        ConsentRequest(
            conversation_id=conversation_id, agent_id=agent_id, account_id=account_for(TEST_USER_EMAIL),
            owner_id=user_id_for(TEST_USER_EMAIL), owner_email=TEST_USER_EMAIL, actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL, tool_use_id="tooluse-1",
            subject=SkillActionSubject(skill_id="social_media", installed_skill_id="social_media", action="publish"),
            key=skill_key("social_media", "publish"), title="Publish to social media", arguments={"text": "hello"},
            preview=ConsentPreview(title="Publish to social media"), editable=["text"],
        )
    )


def _decide(test_client: TestClient, headers: dict, agent_id: str, conversation_id: str, consent_id: str, body: dict):
    with test_client.stream(
        "POST", f"/agents/{agent_id}/{conversation_id}/consents/{consent_id}/decision", json=body, headers=headers
    ) as response:
        list(response.iter_lines())
        return response


def test_rejecting_a_card_starts_the_turn_that_carries_on_from_it(test_client, auth_headers, monkeypatch):
    architecture = _RecordingArchitecture()
    monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: architecture)
    agent_id, conversation_id = _chat(test_client, auth_headers)
    request = _pending(agent_id, conversation_id)

    response = _decide(test_client, auth_headers, agent_id, conversation_id, request.consent_id,
                       {"decision": "reject", "reason": "Not today"})

    assert response.status_code == 200 and response.headers["X-Turn-Id"]
    assert ConsentRepository().get(request.consent_id).status is ConsentStatus.REJECTED
    [turn] = architecture.turns
    assert 'decision="rejected"' in turn["user_message"] and "Not today" in turn["user_message"]

    listed = test_client.get(f"/agents/{agent_id}/{conversation_id}/consents", headers=auth_headers).json()
    assert [(card["consent_id"], card["state"]) for card in listed] == [(request.consent_id, "rejected")]


def test_a_decided_card_cannot_be_decided_again_and_edits_must_be_editable(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: _RecordingArchitecture())
    agent_id, conversation_id = _chat(test_client, auth_headers)
    request = _pending(agent_id, conversation_id)

    bad_edit = _decide(test_client, auth_headers, agent_id, conversation_id, request.consent_id,
                       {"decision": "approve", "edits": {"accounts": "all"}})
    assert bad_edit.status_code == 400
    assert ConsentRepository().get(request.consent_id).status is ConsentStatus.PENDING

    _decide(test_client, auth_headers, agent_id, conversation_id, request.consent_id, {"decision": "reject"})
    again = _decide(test_client, auth_headers, agent_id, conversation_id, request.consent_id, {"decision": "reject"})
    assert again.status_code == 409


def test_only_the_owner_decides(test_client, auth_headers):
    agent_id, conversation_id = _chat(test_client, auth_headers)
    request = _pending(agent_id, conversation_id)
    # Someone else can't even reach the conversation
    other = _decide(test_client, _headers_for(TEST_USER_EMAIL_2), agent_id, conversation_id, request.consent_id,
                    {"decision": "approve"})
    assert other.status_code == 404
    assert ConsentRepository().get(request.consent_id).status is ConsentStatus.PENDING


def test_always_allow_is_listed_set_and_cleared_per_action(test_client, auth_headers):
    agent_id, _ = _chat(test_client, auth_headers)
    AgentSkillRepository().save(AgentSkill(
        agent_id=agent_id, installed_skill_id="social_media", skill_id="social_media", namespace="integrations.social",
        skill_name="Social media", skill_description="Posts.", installed_by=TEST_USER_EMAIL,
    ))

    def listed():
        return {item["key"]: item["always_allowed"] for item in
                test_client.get(f"/agents/{agent_id}/standing-consents", headers=auth_headers).json()}

    key = skill_key("social_media", "publish")
    assert listed() == {key: False}
    assert test_client.put(f"/agents/{agent_id}/standing-consents/{key}", headers=auth_headers).status_code == 204
    assert listed() == {key: True}
    assert test_client.delete(f"/agents/{agent_id}/standing-consents/{key}", headers=auth_headers).status_code == 204
    assert listed() == {key: False}
    assert test_client.put(f"/agents/{agent_id}/standing-consents/skill:nope.x", headers=auth_headers).status_code == 404
