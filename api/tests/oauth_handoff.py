"""Connect callbacks hand off to the SPA, which completes them signed in (see src/auth/oauth_handoff.py)."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt

from tests.mock_data import TEST_USER_EMAIL


def owner_headers(email: str = TEST_USER_EMAIL) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    token = jwt.encode({"aud": "owner", "sub": email, "iat": now, "exp": now + timedelta(hours=1)}, "test-secret")
    return {"Authorization": f"Bearer {token}"}


def handoff_result(test_client, callback_response, email: str = TEST_USER_EMAIL) -> dict[str, list[str]]:
    """Complete the callback's handoff as `email`; the result in parse_qs shape, as the page reads it."""
    blob = parse_qs(urlparse(callback_response.headers["location"]).query)["oauth_complete"][0]
    response = test_client.post("/connectors/oauth/complete", json={"completion": blob}, headers=owner_headers(email))
    assert response.status_code == 200, response.text
    return {key: [value] for key, value in response.json()["result"].items()}
