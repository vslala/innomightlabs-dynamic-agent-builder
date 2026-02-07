import json

from fastapi import status


def test_manifest_rejects_http_tool_missing_http_spec(test_client, auth_headers, dynamodb_table, skills_s3_bucket):
    manifest = {
        "skill_id": "bad",
        "name": "Bad",
        "version": "1.0.0",
        "description": "",
        "allowed_hosts": ["example.com"],
        "tools": [
            {
                "name": "x",
                "description": "",
                "parameters": {"type": "object", "properties": {}},
                "executor": "http"
                # missing http: {...}
            }
        ],
    }

    resp = test_client.post(
        "/skills/manifest",
        json={"manifest_json": json.dumps(manifest), "skill_md": ""},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_manifest_accepts_http_tool_with_valid_http_spec(test_client, auth_headers, dynamodb_table, skills_s3_bucket):
    manifest = {
        "skill_id": "ok",
        "name": "Ok",
        "version": "1.0.0",
        "description": "",
        "allowed_hosts": ["example.com"],
        "tools": [
            {
                "name": "x",
                "description": "",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                "executor": "http",
                "http": {"method": "GET", "url": "https://example.com/"},
            }
        ],
    }

    resp = test_client.post(
        "/skills/manifest",
        json={"manifest_json": json.dumps(manifest), "skill_md": ""},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED
