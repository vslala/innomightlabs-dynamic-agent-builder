"""LinkedIn company pages. Posting as a page is a different LinkedIn product (the Community Management API, with its own
review) and so its own OAuth app: this network has its own client id and secret, but is otherwise LinkedIn, so it
inherits connecting, posting and revoking from `LinkedInNetwork`.

One sign-in connects every page the member administers, one account each. They share the member's token, so
reconnecting any of them refreshes all of them.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.connectors.social.networks.base import ConnectedProfile, ConnectError
from src.connectors.social.networks.linkedin import (
    API_VERSION,
    TIMEOUT_SECONDS,
    LinkedInNetwork,
    _expiry,
    _json,
)

ACLS_URL = "https://api.linkedin.com/rest/organizationAcls"
ORGANIZATIONS_URL = "https://api.linkedin.com/rest/organizations"
#: The roles that may publish for a page
POSTING_ROLES = {"ADMINISTRATOR", "CONTENT_ADMIN"}
ORGANIZATION_PREFIX = "urn:li:organization:"


class LinkedInPagesNetwork(LinkedInNetwork):
    key = "linkedin_page"
    display_name = "LinkedIn Pages"
    description = "Post as a company page you administer."
    shares_grant = True
    app = "linked_in_pages"
    scopes = "r_organization_admin w_organization_social"

    async def complete(self, code: str, code_verifier: str) -> list[ConnectedProfile]:
        async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
            tokens = await self._exchange(client, code)
            headers = {
                "Authorization": f"Bearer {tokens['access_token']}",
                "LinkedIn-Version": API_VERSION,
                "X-Restli-Protocol-Version": "2.0.0",
            }
            page_ids = await self._administered_pages(client, headers)
            if not page_ids:
                raise ConnectError("That LinkedIn account doesn't administer any pages it can post as")
            names = {page_id: await self._page(client, headers, page_id) for page_id in page_ids}

        expires_at = _expiry(tokens)
        return [
            ConnectedProfile(
                external_id=page_id,
                handle=handle,
                display_name=name,
                avatar_url=None,
                credentials={
                    "access_token": tokens["access_token"],
                    "expires_at": expires_at.isoformat(),
                    "author_urn": f"{ORGANIZATION_PREFIX}{page_id}",
                },
                scopes=str(tokens.get("scope") or self.scopes),
                expires_at=expires_at,
            )
            for page_id, (name, handle) in names.items()
        ]

    async def _administered_pages(self, client: httpx.AsyncClient, headers: dict[str, str]) -> list[str]:
        response = await client.get(ACLS_URL, params={"q": "roleAssignee", "state": "APPROVED", "count": 100}, headers=headers)
        if response.status_code != 200:
            raise ConnectError(f"LinkedIn did not list the member's pages ({response.status_code})")
        pages = (
            str(element["organization"]).removeprefix(ORGANIZATION_PREFIX)
            for element in _json(response).get("elements", [])
            if element.get("role") in POSTING_ROLES and str(element.get("organization", "")).startswith(ORGANIZATION_PREFIX)
        )
        return list(dict.fromkeys(pages))

    async def _page(self, client: httpx.AsyncClient, headers: dict[str, str], page_id: str) -> tuple[str, str]:
        """(name, handle). A page whose details can't be read is still postable, so it keeps a plain name."""
        response = await client.get(f"{ORGANIZATIONS_URL}/{page_id}", headers=headers)
        details: dict[str, Any] = _json(response) if response.status_code == 200 else {}
        name = str(details.get("localizedName") or f"LinkedIn page {page_id}")
        vanity = str(details.get("vanityName") or "")
        return name, f"@{vanity}" if vanity else name
