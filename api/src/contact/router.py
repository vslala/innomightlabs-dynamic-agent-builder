"""Contact form router for user submissions."""
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from src.email import send_email
from .rate_limiter import check_rate_limit, record_submission
from .github_service import ENQUIRIES_REPO, GitHubService, format_contact_issue_body, get_labels_for_type

log = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])

# Where people can email us directly, and where replies to enquiry confirmations go.
ENQUIRY_INBOX = "hello@innomight.com"


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


EnquiryTopic = Literal["project", "public-sector", "product", "partnership", "other"]

ENQUIRY_TOPIC_NAMES: dict[EnquiryTopic, str] = {
    "project": "a new software project",
    "public-sector": "a public-sector tender or contract",
    "product": "one of our products",
    "partnership": "partnering with us",
    "other": "something else",
}


class Enquiry(BaseModel):
    """A new-business enquiry from the innomight.com contact form."""

    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    organisation: str = Field("", max_length=160)
    topic: EnquiryTopic
    message: str = Field(..., min_length=20, max_length=5000)
    # Honeypot: hidden from people by the form, so only bots fill it in.
    website: str = ""

    @property
    def is_spam(self) -> bool:
        return bool(self.website.strip())

    @property
    def issue_title(self) -> str:
        organisation = f" ({self.organisation})" if self.organisation else ""
        return f"Enquiry from {self.name}{organisation}"

    @property
    def issue_body(self) -> str:
        return f"""**From:** {self.name} <{self.email}>
**Organisation:** {self.organisation or "-"}
**Topic:** {ENQUIRY_TOPIC_NAMES[self.topic]}

---

{self.message}

---
*Submitted via the innomight.com contact form*
"""

    @property
    def issue_labels(self) -> list[str]:
        return ["enquiry", self.topic]

    @property
    def confirmation_body(self) -> str:
        return f"""Hi {self.name},

Thanks for getting in touch with Innomight Labs. We've received your message about {ENQUIRY_TOPIC_NAMES[self.topic]} and will reply within two working days.

For your reference, here is what you sent:

{self.message}

If you need to add anything, just reply to this email.

Innomight Labs
https://innomight.com
"""


class EnquiryResponse(BaseModel):
    message: str


@router.post("/enquiry", response_model=EnquiryResponse)
async def submit_enquiry(enquiry: Enquiry, request: Request) -> EnquiryResponse:
    """
    Record a contact-form enquiry as an issue in the private enquiries repo, then email the
    sender a confirmation.

    Shares the contact rate limit: one submission per 5 minutes per IP address.
    """
    thanks = EnquiryResponse(message="Thanks for getting in touch. We'll reply within two working days.")

    # Bots get the same response as people so they can't tell they were filtered.
    if enquiry.is_spam:
        log.info("Dropped contact enquiry that filled the honeypot field")
        return thanks

    client_ip = request.client.host if request.client else "unknown"
    is_allowed, seconds_remaining = check_rate_limit(client_ip, window_seconds=300)
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"You've already sent us a message. Please wait {seconds_remaining} seconds before sending another.",
        )

    # The issue is the record of the enquiry, so failing to create it fails the submission.
    try:
        issue = await GitHubService().create_issue(
            title=enquiry.issue_title,
            body=enquiry.issue_body,
            labels=enquiry.issue_labels,
            repo=ENQUIRIES_REPO,
        )
    except Exception as e:
        log.error(f"✗ Error recording contact enquiry: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"We couldn't send your message just now. Please email us at {ENQUIRY_INBOX}.",
        )

    record_submission(client_ip, window_seconds=300)
    log.info(f"✓ Contact enquiry recorded: topic={enquiry.topic}, issue=#{issue['number']}")

    # The confirmation is a courtesy: the enquiry is already recorded, so a failed email isn't fatal.
    confirmed = send_email(
        enquiry.email,
        "We've received your message",
        enquiry.confirmation_body,
        reply_to=ENQUIRY_INBOX,
        sender_name="Innomight Labs",
    )
    if not confirmed:
        log.warning(f"Failed to send enquiry confirmation for issue #{issue['number']}")

    return thanks
