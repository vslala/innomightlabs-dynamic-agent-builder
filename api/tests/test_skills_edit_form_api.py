import json

from fastapi import status


def test_get_edit_form_returns_manifest_skill_md_and_secret_names(
    test_client, auth_headers, dynamodb_table, skills_s3_bucket
):
    manifest = {
        "skill_id": "demo",
        "name": "Demo",
        "version": "1.0.0",
        "description": "",
        "allowed_hosts": ["example.com"],
        "tools": [],
    }

    # create
    resp = test_client.post(
        "/skills/manifest",
        json={
            "manifest_json": json.dumps(manifest),
            "skill_md": "# hello",
            "secrets": [{"name": "wp_token", "value": "SECRET"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED

    # fetch edit form
    resp = test_client.get("/skills/demo/1.0.0/edit-form", headers=auth_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert "form_schema" in payload
    assert "initial_values" in payload

    iv = payload["initial_values"]
    assert "manifest_json" in iv
    assert "skill_md" in iv
    assert "secrets" in iv

    # secrets should only include names (no values returned)
    assert any(s.get("name") == "wp_token" for s in iv["secrets"])
    assert all((s.get("value") in ("", None)) for s in iv["secrets"])


def test_update_skill_manifest_rotates_secret_if_value_provided(
    test_client, auth_headers, dynamodb_table, skills_s3_bucket
):
    manifest = {
        "skill_id": "demo",
        "name": "Demo",
        "version": "1.0.0",
        "description": "",
        "allowed_hosts": ["example.com"],
        "tools": [],
    }

    resp = test_client.post(
        "/skills/manifest",
        json={
            "manifest_json": json.dumps(manifest),
            "skill_md": "# hello",
            "secrets": [{"name": "wp_token", "value": "OLD"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED

    # update with new secret
    resp = test_client.put(
        "/skills/demo/1.0.0",
        json={
            "manifest_json": json.dumps({**manifest, "description": "updated"}),
            "skill_md": "# updated",
            "secrets": [{"name": "wp_token", "value": "NEW"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "updated"

    # verify secret changed
    from src.skills.secrets_repository import SkillSecretsRepository
    from src.crypto import decrypt
    from tests.mock_data import TEST_USER_EMAIL

    repo = SkillSecretsRepository()
    s = repo.get(TEST_USER_EMAIL, "demo", "wp_token")
    assert s is not None
    assert decrypt(s.encrypted_value) == "NEW"
