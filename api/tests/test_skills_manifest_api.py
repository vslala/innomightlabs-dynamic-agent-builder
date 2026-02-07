import json

from fastapi import status


def test_create_skill_from_manifest_then_activate(test_client, auth_headers, dynamodb_table, skills_s3_bucket):
    manifest = {
        "skill_id": "http_get_post",
        "name": "HTTP GET/POST",
        "version": "1.0.0",
        "description": "Generic http",
        "tools": [],
        "allowed_hosts": ["example.com"],
    }

    resp = test_client.post(
        "/skills/manifest",
        json={
            "manifest_json": json.dumps(manifest),
            "skill_md": "# HTTP\n",
        },
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["skill_id"] == "http_get_post"

    resp = test_client.post("/skills/http_get_post/1.0.0/activate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
