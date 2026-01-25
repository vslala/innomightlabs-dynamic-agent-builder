"""Email service module for sending emails via Mailjet."""
from .service import EmailService, EmailTemplate
from .helpers import (
    send_welcome_email_safe,
    send_subscription_confirmed_email_safe,
    send_payment_failed_email_safe,
    send_subscription_upgraded_email_safe,
    send_subscription_cancelled_email_safe,
)

__all__ = [
    "EmailService",
    "EmailTemplate",
    "send_welcome_email_safe",
    "send_subscription_confirmed_email_safe",
    "send_payment_failed_email_safe",
    "send_subscription_upgraded_email_safe",
    "send_subscription_cancelled_email_safe",
]
