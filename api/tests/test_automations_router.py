from datetime import datetime, timedelta, timezone

from src.automations.models import AutomationRun, AutomationRunStatus
from src.automations.repository import AutomationRepository
from tests.mock_data import AUTOMATION_CREATE_REQUEST
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


def test_create_list_get_and_delete_automation(test_client, auth_headers):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    graph = create_response.json()
    automation_id = graph["automation"]["automation_id"]
    assert graph["automation"]["title"] == AUTOMATION_CREATE_REQUEST["title"]
    assert {node["type"] for node in graph["nodes"]} == {"start", "final"}
    assert graph["triggers"][0]["type"] == "manual"

    list_response = test_client.get("/automations", headers=auth_headers)
    assert list_response.status_code == 200
    assert [item["automation_id"] for item in list_response.json()] == [automation_id]

    get_response = test_client.get(f"/automations/{automation_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["automation_id"] == automation_id

    delete_response = test_client.delete(f"/automations/{automation_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    missing_response = test_client.get(f"/automations/{automation_id}", headers=auth_headers)
    assert missing_response.status_code == 404


def test_save_graph_rejects_invalid_graph(test_client, auth_headers):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]

    response = test_client.put(
        f"/automations/{automation_id}/graph",
        json={
            "nodes": [{"node_id": "start", "type": "start", "name": "Start"}],
            "edges": [],
            "triggers": [],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "final" in response.json()["detail"]


def test_list_runs_requires_owner_scoped_automation(test_client, auth_headers):
    response = test_client.get("/automations/missing/runs", headers=auth_headers)

    assert response.status_code == 404


def test_test_run_returns_accepted_run_id(test_client, auth_headers, monkeypatch):
    dispatched = {}

    def fake_invoke(run_id: str, automation_id: str, user_email: str) -> None:
        dispatched["run_id"] = run_id
        dispatched["automation_id"] = automation_id
        dispatched["user_email"] = user_email

    monkeypatch.setattr("src.automations.router.invoke_automation_run_async", fake_invoke)

    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]

    response = test_client.post(
        f"/automations/{automation_id}/test-run",
        json={"input": {"input": "hello"}},
        headers=auth_headers,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["run_id"]
    assert payload["automation_id"] == automation_id
    assert payload["status"] == "pending"
    assert dispatched == {
        "run_id": payload["run_id"],
        "automation_id": automation_id,
        "user_email": TEST_USER_EMAIL,
    }

    detail_response = test_client.get(
        f"/automations/{automation_id}/runs/{payload['run_id']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["run"]["run_id"] == payload["run_id"]
    assert detail["context"]["input"] == {"input": "hello"}


def test_get_run_marks_expired_heartbeat_run_failed(test_client, auth_headers):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]
    run = AutomationRun(
        automation_id=automation_id,
        status=AutomationRunStatus.RUNNING,
        context={"nodes": {}},
        created_by=TEST_USER_EMAIL,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=31),
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=31),
        current_node_id="slow-node",
    )
    AutomationRepository().save_run(run)

    response = test_client.get(
        f"/automations/{automation_id}/runs/{run.run_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["status"] == "failed"
    assert "heartbeat expired" in payload["run"]["error"]
    assert "slow-node" in payload["run"]["error"]
    assert payload["run"]["completed_at"] is not None


def test_get_run_keeps_old_run_with_fresh_heartbeat_running(test_client, auth_headers):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]
    run = AutomationRun(
        automation_id=automation_id,
        status=AutomationRunStatus.RUNNING,
        context={"nodes": {}},
        created_by=TEST_USER_EMAIL,
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        last_heartbeat_at=datetime.now(timezone.utc),
        current_node_id="slow-node",
    )
    AutomationRepository().save_run(run)

    response = test_client.get(
        f"/automations/{automation_id}/runs/{run.run_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["status"] == "running"
    assert payload["run"]["current_node_id"] == "slow-node"
    assert payload["run"]["completed_at"] is None


def test_automation_skills_and_action_catalog(test_client, auth_headers, dynamodb_table):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]

    catalog_response = test_client.get(
        f"/automations/{automation_id}/action-catalog",
        headers=auth_headers,
    )
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    invoke_action = next(item for item in catalog["actions"] if item["skill_id"] == "agent_invocation")
    assert invoke_action["action"] == "invoke"
    assert invoke_action["action_form"]["form_name"] == "Invoke Agent"
    assert not any(
        item["skill_id"] == "scheduler" and item["action"] == "create_or_update"
        for item in catalog["actions"]
    )
    assert not any(
        item["skill_id"] == "scheduler" and item["action"] == "schedule_automation"
        for item in catalog["actions"]
    )

    missing_connector_response = test_client.post(
        f"/automations/{automation_id}/skills?skill_id=google_mail",
        json={"config": {}},
        headers=auth_headers,
    )
    assert missing_connector_response.status_code == 422

    ProviderSettingsRepository().save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleMail",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )
    ProviderSettingsRepository().save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleDrive",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )

    catalog_response = test_client.get(
        f"/automations/{automation_id}/action-catalog",
        headers=auth_headers,
    )
    catalog = catalog_response.json()
    assert any(item["skill_id"] == "google_mail" and item["action"] == "search" for item in catalog["actions"])
    assert any(item["skill_id"] == "google_drive" and item["action"] == "search" for item in catalog["actions"])

    enable_response = test_client.post(
        f"/automations/{automation_id}/skills?skill_id=google_mail",
        json={"config": {}},
        headers=auth_headers,
    )
    assert enable_response.status_code == 201
    assert enable_response.json()["skill_id"] == "google_mail"

    catalog_response = test_client.get(
        f"/automations/{automation_id}/action-catalog",
        headers=auth_headers,
    )
    catalog = catalog_response.json()
    gmail_search = next(item for item in catalog["actions"] if item["skill_id"] == "google_mail" and item["action"] == "search")
    assert gmail_search["action_form"]["form_name"] == "Gmail Search"


def test_action_catalog_shows_config_required_skills_disabled(test_client, auth_headers, dynamodb_table):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]

    catalog_response = test_client.get(
        f"/automations/{automation_id}/action-catalog",
        headers=auth_headers,
    )

    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    send_email = next(
        item
        for item in catalog["actions"]
        if item["skill_id"] == "send_email" and item["action"] == "send"
    )
    assert send_email["available"] is False
    assert send_email["configured"] is False
    assert send_email["enabled"] is False
    assert send_email["disabled_reason"] == "Skill requires configuration before use"
    assert send_email["install_schema"]["form_inputs"][0]["name"] == "to"


def test_repeatable_automation_skill_instances_appear_as_actions(
    test_client,
    auth_headers,
    dynamodb_table,
):
    create_response = test_client.post(
        "/automations",
        json=AUTOMATION_CREATE_REQUEST,
        headers=auth_headers,
    )
    automation_id = create_response.json()["automation"]["automation_id"]

    first = test_client.post(
        f"/automations/{automation_id}/skills?skill_id=send_email",
        json={"config": {"to": "first@example.com"}},
        headers=auth_headers,
    )
    second = test_client.post(
        f"/automations/{automation_id}/skills?skill_id=send_email",
        json={"config": {"to": "second@example.com"}},
        headers=auth_headers,
    )
    duplicate = test_client.post(
        f"/automations/{automation_id}/skills?skill_id=send_email",
        json={"config": {"to": "first@example.com"}},
        headers=auth_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate.status_code == 201
    first_id = first.json()["installed_skill_id"]
    second_id = second.json()["installed_skill_id"]
    assert first_id.startswith("send_email:")
    assert second_id.startswith("send_email:")
    assert first_id != second_id
    assert duplicate.json()["installed_skill_id"] == first_id

    skills_response = test_client.get(
        f"/automations/{automation_id}/skills",
        headers=auth_headers,
    )
    installed_send_email = [
        item for item in skills_response.json() if item["skill_id"] == "send_email"
    ]
    assert [item["installed_skill_id"] for item in installed_send_email] == [
        first_id,
        second_id,
    ]

    catalog_response = test_client.get(
        f"/automations/{automation_id}/action-catalog",
        headers=auth_headers,
    )
    catalog = catalog_response.json()
    send_actions = [
        item
        for item in catalog["actions"]
        if item["skill_id"] == "send_email" and item["action"] == "send"
    ]
    assert [item["installed_skill_id"] for item in send_actions] == [first_id, second_id]
    assert all(item["available"] is True for item in send_actions)
    assert all(item["configured"] is True for item in send_actions)
