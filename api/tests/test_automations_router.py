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
