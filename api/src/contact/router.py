"""Contact form router for user submissions."""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from .rate_limiter import check_rate_limit, record_submission
from .github_service import GitHubService, format_contact_issue_body, get_labels_for_type

log = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])


class ContactSubmission(BaseModel):
    """Contact form submission model."""

    type: str = Field(
        ...,
        description="Submission type: feedback, support, bug-report, or feature-request"
    )
    subject: str = Field(..., min_length=5, max_length=200, description="Subject/title")
    email: EmailStr = Field(..., description="Submitter's email address")
    description: str = Field(..., min_length=20, max_length=5000, description="Detailed description")


class ContactResponse(BaseModel):
    """Response after successful contact form submission."""

    success: bool
    message: str
    issue_number: int
    issue_url: str


@router.post("/submit", response_model=ContactResponse)
async def submit_contact_form(
    submission: ContactSubmission,
    request: Request,
) -> ContactResponse:
    """
    Submit contact form and create GitHub issue.

    Rate limited to 1 submission per 5 minutes per IP address.
    """
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    is_allowed, seconds_remaining = check_rate_limit(client_ip, window_seconds=300)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {seconds_remaining} seconds before submitting again."
        )

    # Validate submission type
    valid_types = ["feedback", "support", "bug-report", "feature-request"]
    if submission.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid submission type. Must be one of: {', '.join(valid_types)}"
        )

    try:
        # Format issue body
        issue_body = format_contact_issue_body(
            email=submission.email,
            submission_type=submission.type,
            description=submission.description,
        )

        # Get labels
        labels = get_labels_for_type(submission.type)

        # Create GitHub issue
        github_service = GitHubService()
        issue_data = await github_service.create_issue(
            title=submission.subject,
            body=issue_body,
            labels=labels,
        )

        # Record submission for rate limiting
        record_submission(client_ip, window_seconds=300)

        log.info(
            f"✓ Contact form submitted: type={submission.type}, "
            f"email={submission.email}, issue=#{issue_data['number']}"
        )

        return ContactResponse(
            success=True,
            message="Thank you for your submission! We'll get back to you soon.",
            issue_number=issue_data["number"],
            issue_url=issue_data["html_url"],
        )

    except ValueError as e:
        # GitHub token not configured
        log.error(f"GitHub token not configured: {e}")
        raise HTTPException(
            status_code=500,
            detail="Contact form is not properly configured. Please try again later."
        )

    except Exception as e:
        log.error(f"✗ Error submitting contact form: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to submit contact form. Please try again later."
        )
