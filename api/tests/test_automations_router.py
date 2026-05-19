from tests.mock_data import AUTOMATION_CREATE_REQUEST


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
