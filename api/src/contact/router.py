"""Contact forms of innomightlabs.com and innomight.com.

Both record every enquiry the same way: an issue in the private enquiries repo labelled with the
site it came from and its category, an email to that site's inbox, and a confirmation to the sender.
"""
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from src.email import send_email
from src.email.message import EmailLink, MessageEmail
from src.rate_limits.limiter import RateLimitPolicy, RateLimiter
from .github_service import GitHubService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])

#: One submission per 5 minutes per IP address, across both forms.
CONTACT_RATE_LIMIT = RateLimitPolicy.cooldown("CONTACT", seconds=300)


@dataclass(frozen=True)
class ContactSite:
    """A site with a contact form, and where its enquiries go."""

    #: GitHub label naming the site an enquiry came from.
    label: str
    name: str
    #: Notified of every enquiry, and where replies to confirmations go.
    inbox: str
    url: str


INNOMIGHTLABS = ContactSite("innomightlabs", "InnomightLabs", "hello@innomightlabs.com", "https://innomightlabs.com")
INNOMIGHT = ContactSite("innomight", "Innomight Labs", "hello@innomight.com", "https://innomight.com")


class ContactEnquiry(Protocol):
    """What the shared pipeline needs from either form."""

    email: str

    @property
    def category(self) -> str: ...

    @property
    def category_name(self) -> str: ...

    @property
    def greeting_name(self) -> str: ...

    @property
    def message(self) -> str: ...

    @property
    def issue_title(self) -> str: ...

    @property
    def issue_body(self) -> str: ...

    @property
    def details(self) -> list[tuple[str, str]]: ...


class ContactResponse(BaseModel):
    success: bool = True
    message: str


async def record_enquiry(enquiry: ContactEnquiry, site: ContactSite, request: Request) -> ContactResponse:
    """Record the enquiry as an issue, tell the site's inbox, and confirm to the sender.

    One submission per 5 minutes per IP address, across both forms.
    """
    client_ip = request.client.host if request.client else "unknown"
    limiter = RateLimiter(CONTACT_RATE_LIMIT)
    # Taken before the work so two simultaneous submissions can't both get through.
    decision = limiter.acquire(client_ip)
    if not decision.allowed:
        wait = f" Please wait {decision.retry_after_seconds} seconds before sending another." if decision.retry_after_seconds else ""
        raise HTTPException(status_code=429, detail=f"You've already sent us a message.{wait}")

    # The issue is the record of the enquiry, so failing to create it fails the submission.
    try:
        issue = await GitHubService().create_issue(
            title=enquiry.issue_title,
            body=f"{enquiry.issue_body}\n---\n*Submitted via the {site.url.removeprefix('https://')} contact form*\n",
            labels=[site.label, enquiry.category],
        )
    except Exception as e:
        log.error(f"✗ Error recording {site.label} enquiry: {e}", exc_info=True)
        # The enquiry wasn't recorded, so it shouldn't stop the sender trying again.
        limiter.release(decision)
        raise HTTPException(
            status_code=502,
            detail=f"We couldn't send your message just now. Please email us at {site.inbox}.",
        )

    log.info(f"✓ Enquiry recorded: site={site.label}, category={enquiry.category}, issue=#{issue['number']}")

    # The issue already holds the enquiry, so neither email failing is fatal.
    notification = _notification(enquiry, site, issue["html_url"])
    if not send_email(
        site.inbox,
        f"New enquiry ({enquiry.category}): {enquiry.issue_title}",
        notification.text(),
        reply_to=enquiry.email,
        sender_name=f"{site.name} contact form",
        html=notification.html(),
    ):
        log.warning(f"Failed to notify {site.inbox} of issue #{issue['number']}")

    confirmation = _confirmation(enquiry, site)
    if not send_email(
        enquiry.email,
        "We've received your message",
        confirmation.text(),
        reply_to=site.inbox,
        sender_name=site.name,
        html=confirmation.html(),
    ):
        log.warning(f"Failed to send enquiry confirmation for issue #{issue['number']}")

    return ContactResponse(message="Thanks for getting in touch. We'll reply within two working days.")


def _notification(enquiry: ContactEnquiry, site: ContactSite, issue_url: str) -> MessageEmail:
    return MessageEmail(
        preheader=enquiry.message[:120],
        heading=enquiry.issue_title,
        paragraphs=[f"A new enquiry about {enquiry.category_name} came in through the {site.name} contact form."],
        details=[("Site", site.url.removeprefix("https://")), *enquiry.details],
        quote=enquiry.message,
        closing=["Reply to this email to answer them directly."],
        action=EmailLink("Open the issue", issue_url),
        footer=_footer(site),
    )


def _confirmation(enquiry: ContactEnquiry, site: ContactSite) -> MessageEmail:
    return MessageEmail(
        preheader="We'll reply within two working days.",
        heading="We've received your message",
        paragraphs=[
            f"Hi {enquiry.greeting_name},",
            f"Thanks for getting in touch with {site.name}. We've received your message about "
            f"{enquiry.category_name} and will reply within two working days.",
            "For your reference, here is what you sent:",
        ],
        quote=enquiry.message,
        closing=["If you need to add anything, just reply to this email."],
        sign_off=site.name,
        footer=_footer(site),
    )


def _footer(site: ContactSite) -> EmailLink:
    return EmailLink(site.name, site.url)


ContactCategory = Literal["sales", "support", "feedback", "bug-report", "feature-request"]

CONTACT_CATEGORY_NAMES: dict[ContactCategory, str] = {
    "sales": "sales and enterprise plans",
    "support": "getting support",
    "feedback": "feedback on InnomightLabs",
    "bug-report": "a bug in InnomightLabs",
    "feature-request": "a feature request",
}


class ContactSubmission(BaseModel):
    """A message from the innomightlabs.com contact form."""

    type: ContactCategory
    subject: str = Field(..., min_length=5, max_length=200)
    email: EmailStr
    description: str = Field(..., min_length=20, max_length=5000)

    @property
    def category(self) -> str:
        return self.type

    @property
    def category_name(self) -> str:
        return CONTACT_CATEGORY_NAMES[self.type]

    @property
    def greeting_name(self) -> str:
        return "there"

    @property
    def message(self) -> str:
        return self.description

    @property
    def issue_title(self) -> str:
        return self.subject

    @property
    def details(self) -> list[tuple[str, str]]:
        return [("From", self.email), ("Category", self.type)]

    @property
    def issue_body(self) -> str:
        return f"""**From:** {self.email}
**Category:** {self.type}

---

{self.description}
"""


@router.post("/submit", response_model=ContactResponse)
async def submit_contact_form(submission: ContactSubmission, request: Request) -> ContactResponse:
    """Record an innomightlabs.com contact form message."""
    return await record_enquiry(submission, INNOMIGHTLABS, request)


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
    def category(self) -> str:
        return self.topic

    @property
    def category_name(self) -> str:
        return ENQUIRY_TOPIC_NAMES[self.topic]

    @property
    def greeting_name(self) -> str:
        return self.name

    @property
    def issue_title(self) -> str:
        organisation = f" ({self.organisation})" if self.organisation else ""
        return f"Enquiry from {self.name}{organisation}"

    @property
    def details(self) -> list[tuple[str, str]]:
        return [
            ("From", f"{self.name} <{self.email}>"),
            ("Organisation", self.organisation or "-"),
            ("Topic", self.topic),
        ]

    @property
    def issue_body(self) -> str:
        return f"""**From:** {self.name} <{self.email}>
**Organisation:** {self.organisation or "-"}
**Topic:** {self.category_name}

---

{self.message}
"""


@router.post("/enquiry", response_model=ContactResponse)
async def submit_enquiry(enquiry: Enquiry, request: Request) -> ContactResponse:
    """Record an innomight.com contact form enquiry."""
    # Bots get the same response as people so they can't tell they were filtered.
    if enquiry.is_spam:
        log.info("Dropped contact enquiry that filled the honeypot field")
        return ContactResponse(message="Thanks for getting in touch. We'll reply within two working days.")
    return await record_enquiry(enquiry, INNOMIGHT, request)
