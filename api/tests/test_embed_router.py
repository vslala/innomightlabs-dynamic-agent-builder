"""
Tests for the embeddable iframe widget: the HTML shell and same-origin widget calls.
"""

import json
import re
from typing import cast

from fastapi.testclient import TestClient

from tests.mock_data import AGENT_CREATE_REQUEST


def _create_agent(test_client: TestClient, auth_headers: dict, **overrides) -> str:
    response = test_client.post("/agents", json={**AGENT_CREATE_REQUEST, **overrides}, headers=auth_headers)
    return cast(str, response.json()["agent_id"])


def _create_widget_key(test_client: TestClient, auth_headers: dict, agent_id: str, allowed_origins: list[str]) -> dict:
    response = test_client.post(
        f"/agents/{agent_id}/api-keys",
        json={"name": "Website", "allowed_origins": allowed_origins},
        headers=auth_headers,
    )
    return cast(dict, response.json())


def _bootstrap(page: str) -> dict:
    match = re.search(r'<script type="application/json" id="innomight-bootstrap">(.*?)</script>', page, re.S)
    assert match, "bootstrap JSON missing"
    return cast(dict, json.loads(match.group(1)))


def _csp(response) -> dict[str, str]:
    directives = [part.strip() for part in response.headers["content-security-policy"].split(";")]
    return {name: value for name, _, value in (directive.partition(" ") for directive in directives)}


class TestEmbedShell:
    def test_renders_shell_with_bootstrap_and_cdn_assets(self, test_client: TestClient, auth_headers: dict):
        from src.config import settings

        agent_id = _create_agent(test_client, auth_headers, agent_name="Support Agent")
        key = _create_widget_key(test_client, auth_headers, agent_id, [])

        response = test_client.get(f"/embed/{key['public_key']}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-store"
        assert f'src="{settings.widget_cdn_url}/embed/app.js"' in response.text
        assert f'href="{settings.widget_cdn_url}/embed/app.css"' in response.text
        assert _bootstrap(response.text) == {
            "public_key": key["public_key"],
            "agent_id": agent_id,
            "agent_name": "Support Agent",
            "agent_description": AGENT_CREATE_REQUEST.get("agent_description"),
            "api_base_url": settings.api_base_url.rstrip("/"),
        }

    def test_needs_no_dashboard_login(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, [])

        assert test_client.get(f"/embed/{key['public_key']}", headers={}).status_code == 200

    def test_frame_ancestors_follow_allowed_origins(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, ["https://example.com", "https://www.example.com"])

        csp = _csp(test_client.get(f"/embed/{key['public_key']}"))

        assert csp["frame-ancestors"] == "https://example.com https://www.example.com"
        assert csp["connect-src"] == "'self'"

    def test_empty_allowed_origins_can_be_framed_anywhere(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, [])

        assert _csp(test_client.get(f"/embed/{key['public_key']}"))["frame-ancestors"] == "*"

    def test_agent_name_cannot_break_out_of_the_page(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers, agent_name="</script><script>alert(1)</script>")
        key = _create_widget_key(test_client, auth_headers, agent_id, [])

        page = test_client.get(f"/embed/{key['public_key']}").text

        assert "<script>alert(1)" not in page
        assert _bootstrap(page)["agent_name"] == "</script><script>alert(1)</script>"

    def test_unknown_key_is_unavailable(self, test_client: TestClient):
        response = test_client.get("/embed/pk_live_does_not_exist")

        assert response.status_code == 404
        assert "unavailable" in response.text

    def test_disabled_key_is_unavailable(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, [])
        test_client.patch(f"/agents/{agent_id}/api-keys/{key['key_id']}", json={"is_active": False}, headers=auth_headers)

        assert test_client.get(f"/embed/{key['public_key']}").status_code == 404


class TestSameOriginWidgetCalls:
    """The iframe calls /widget/* from the API's own origin, which a key's allowed origins never list."""

    def test_same_origin_request_passes_origin_restriction(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, ["https://example.com"])

        response = test_client.get(
            "/widget/config", headers={"X-API-Key": key["public_key"], "Sec-Fetch-Site": "same-origin"}
        )

        assert response.status_code == 200

    def test_cross_origin_request_is_still_restricted(self, test_client: TestClient, auth_headers: dict):
        agent_id = _create_agent(test_client, auth_headers)
        key = _create_widget_key(test_client, auth_headers, agent_id, ["https://example.com"])

        blocked = test_client.get(
            "/widget/config",
            headers={"X-API-Key": key["public_key"], "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
        )
        allowed = test_client.get(
            "/widget/config", headers={"X-API-Key": key["public_key"], "Origin": "https://example.com"}
        )

        assert blocked.status_code == 403
        assert allowed.status_code == 200
