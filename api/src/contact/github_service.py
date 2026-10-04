"""GitHub issue creation service for contact form submissions."""
import logging
import httpx
from typing import Any, List, cast

from src.config import settings

log = logging.getLogger(__name__)


GITHUB_API_URL = "https://api.github.com"
REPO_OWNER = "vslala"
# Every contact form enquiry carries personal details, so they all go to a private repo.
ENQUIRIES_REPO = "innomightlabs-enquiries"


class GitHubService:
    """Service for creating GitHub issues."""

    def __init__(self):
        """Initialize GitHub service with API token."""
        self.token = settings.github_token
        if not self.token:
            log.warning("GitHub token not configured, issue creation will fail")

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: List[str],
        repo: str = ENQUIRIES_REPO,
    ) -> dict:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body (markdown supported)
            labels: List of label names
            repo: Repository under REPO_OWNER to create the issue in

        Returns:
            GitHub issue response dict

        Raises:
            httpx.HTTPStatusError: If GitHub API request fails
        """
        if not self.token:
            raise ValueError("GitHub token not configured")

        url = f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{repo}/issues"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {
            "title": title,
            "body": body,
            "labels": labels,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            issue_data = response.json()
            if not isinstance(issue_data, dict):
                raise ValueError("GitHub issue response was not an object")

            log.info(f"✓ Created GitHub issue #{issue_data['number']}: {title}")
            return cast(dict[Any, Any], issue_data)

