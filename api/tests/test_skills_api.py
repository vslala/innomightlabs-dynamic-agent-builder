import io
import json
import zipfile

from fastapi import status


def _make_skill_zip(skill_id: str = "wordpress", version: str = "1.0.0") -> bytes:
    manifest = {
        "skill_id": skill_id,
        "name": "WordPress",
        "version": version,
        "description": "Search blog posts",
        "tools": [
            {
                "name": "wp_search_posts",
                "description": "Search posts",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                "executor": "http",
                "http": {
                    "method": "GET",
                    "url": "https://www.bemyaficionado.com/wp-json/wp/v2/posts",
                    "query": {"search": "{{query}}"}
                }
            }
        ],
        "allowed_hosts": ["www.bemyaficionado.com"],
    }
    skill_md = "# WordPress Skill\nUse wp_search_posts"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("SKILL.md", skill_md)
    return buf.getvalue()


def test_upload_list_activate_deactivate_skill(test_client, auth_headers, dynamodb_table, skills_s3_bucket):
    zip_bytes = _make_skill_zip()

    files = {"file": ("wordpress.zip", zip_bytes, "application/zip")}
    resp = test_client.post("/skills/upload", files=files, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["skill_id"] == "wordpress"
    assert data["status"] == "inactive"

    # list
    resp = test_client.get("/skills", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1

    # activate
    resp = test_client.post("/skills/wordpress/1.0.0/activate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # deactivate
    resp = test_client.post("/skills/wordpress/1.0.0/deactivate", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"
