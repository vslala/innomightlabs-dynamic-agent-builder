"""Email service module for sending emails via Mailjet."""
from importlib import import_module
import logging
from src.config import settings

from .service import EmailService, EmailTemplate
from .helpers import (
    send_welcome_email_safe,
    send_subscription_confirmed_email_safe,
    send_payment_failed_email_safe,
    send_subscription_upgraded_email_safe,
    send_subscription_cancelled_email_safe,
)

log = logging.getLogger(__name__)
Client = import_module("mailjet_rest").Client


def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    sender_name: str = "InnomightLabs",
) -> bool:
    """
    Send a simple plain text email via Mailjet.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Plain text email body
        reply_to: Optional address that replies should go to instead of the sender
        sender_name: Display name shown as the sender

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        client = Client(
            auth=(settings.mailjet_api_key, settings.mailjet_secret_key),
            version="v3.1",
        )

        message: dict[str, object] = {
            "From": {"Email": "noreply@innomightlabs.com", "Name": sender_name},
            "To": [{"Email": to_email}],
            "Subject": subject,
            "TextPart": body,
        }
        if reply_to:
            message["ReplyTo"] = {"Email": reply_to}

        data = {"Messages": [message]}

        result = client.send.create(data=data)

        if result.status_code == 200:
            log.info(f"Email sent to {to_email}: {subject}")
            return True
        else:
            log.warning(f"Failed to send email to {to_email}: {result.status_code}")
            return False

    except Exception as e:
        log.error(f"Error sending email to {to_email}: {e}")
        return False


__all__ = [
    "EmailService",
    "EmailTemplate",
    "send_email",
    "send_welcome_email_safe",
    "send_subscription_confirmed_email_safe",
    "send_payment_failed_email_safe",
    "send_subscription_upgraded_email_safe",
    "send_subscription_cancelled_email_safe",
]
