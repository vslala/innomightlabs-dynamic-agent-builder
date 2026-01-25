"""GitHub issue creation service for contact form submissions."""
import logging
import httpx
from typing import List

from src.config import settings

log = logging.getLogger(__name__)


GITHUB_API_URL = "https://api.github.com"
REPO_OWNER = "vslala"
REPO_NAME = "innomightlabs-dynamic-agent-builder"


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
    ) -> dict:
        """
        Create a GitHub issue.

        Args:
            title: Issue title
            body: Issue body (markdown supported)
            labels: List of label names

        Returns:
            GitHub issue response dict

        Raises:
            httpx.HTTPStatusError: If GitHub API request fails
        """
        if not self.token:
            raise ValueError("GitHub token not configured")

        url = f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/issues"
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

            log.info(f"✓ Created GitHub issue #{issue_data['number']}: {title}")
            return issue_data


def format_contact_issue_body(
    email: str,
    submission_type: str,
    description: str,
) -> str:
    """
    Format contact form submission as GitHub issue body.

    Args:
        email: Submitter's email
        submission_type: Type of submission (feedback, support, bug-report, feature-request)
        description: User's description

    Returns:
        Formatted markdown string
    """
    return f"""**From:** {email}
**Type:** {submission_type}

---

{description}

---
*Submitted via contact form*
"""


def get_labels_for_type(submission_type: str) -> List[str]:
    """
    Get GitHub labels based on submission type.

    Args:
        submission_type: One of: feedback, support, bug-report, feature-request

    Returns:
        List of label names
    """
    type_label_map = {
        "feedback": ["feedback", "user-submitted"],
        "support": ["support", "user-submitted"],
        "bug-report": ["bug-report", "user-submitted"],
        "feature-request": ["feature-request", "user-submitted"],
    }

    return type_label_map.get(submission_type, ["user-submitted"])
