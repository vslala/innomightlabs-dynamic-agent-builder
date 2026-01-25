"""Email service using Mailjet API."""
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

from mailjet_rest import Client

from src.config import settings

log = logging.getLogger(__name__)


class EmailTemplate(Enum):
    """Email template identifiers."""

    WELCOME = "welcome"
    SUBSCRIPTION_CONFIRMED = "subscription_confirmed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    PAYMENT_FAILED = "payment_failed"


class EmailService:
    """Service for sending emails via Mailjet."""

    def __init__(self):
        """Initialize Mailjet client."""
        self.client = Client(
            auth=(settings.mailjet_api_key, settings.mailjet_secret_key),
            version="v3.1",
        )
        self.from_email = "noreply@innomightlabs.com"
        self.from_name = "InnomightLabs"
        self.templates_dir = Path(__file__).parent.parent.parent / "assets" / "templates" / "emails"

    def _load_template(self, template: EmailTemplate) -> str:
        """Load HTML email template from file."""
        template_path = self.templates_dir / f"{template.value}.html"
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            log.error(f"Email template not found: {template_path}")
            raise

    def _replace_variables(self, html: str, variables: Dict[str, str]) -> str:
        """Replace template variables with actual values."""
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            html = html.replace(placeholder, str(value))
        return html

    async def send_email(
        self,
        to_email: str,
        subject: str,
        template: EmailTemplate,
        variables: Dict[str, str],
    ) -> bool:
        """
        Send email using Mailjet API.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            template: Email template to use
            variables: Template variables to substitute

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Load and prepare template
            html_content = self._load_template(template)
            html_content = self._replace_variables(html_content, variables)

            # Prepare email data
            data = {
                "Messages": [
                    {
                        "From": {"Email": self.from_email, "Name": self.from_name},
                        "To": [{"Email": to_email}],
                        "Subject": subject,
                        "HTMLPart": html_content,
                    }
                ]
            }

            # Send via Mailjet
            result = self.client.send.create(data=data)

            if result.status_code == 200:
                log.info(f"Email sent successfully to {to_email}: {subject}")
                return True
            else:
                log.error(
                    f"Failed to send email to {to_email}. "
                    f"Status: {result.status_code}, Response: {result.json()}"
                )
                return False

        except Exception as e:
            log.error(f"Error sending email to {to_email}: {e}", exc_info=True)
            return False

    async def send_welcome_email(self, to_email: str, user_name: str) -> bool:
        """Send welcome email to new user."""
        variables = {
            "user_name": user_name,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
        }
        return await self.send_email(
            to_email=to_email,
            subject="Welcome to InnomightLabs! 🎉",
            template=EmailTemplate.WELCOME,
            variables=variables,
        )

    async def send_subscription_confirmed_email(
        self,
        to_email: str,
        user_name: str,
        plan_name: str,
        amount: str,
        billing_period: str,
        next_charge_date: str,
    ) -> bool:
        """Send subscription confirmation email."""
        variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": amount,
            "billing_period": billing_period,
            "next_charge_date": next_charge_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }
        return await self.send_email(
            to_email=to_email,
            subject=f"Subscription Confirmed - {plan_name.title()} Plan",
            template=EmailTemplate.SUBSCRIPTION_CONFIRMED,
            variables=variables,
        )

    async def send_subscription_cancelled_email(
        self,
        to_email: str,
        user_name: str,
        plan_name: str,
        access_until: str,
    ) -> bool:
        """Send subscription cancellation email."""
        variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "access_until": access_until,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }
        return await self.send_email(
            to_email=to_email,
            subject="Subscription Cancelled",
            template=EmailTemplate.SUBSCRIPTION_CANCELLED,
            variables=variables,
        )

    async def send_subscription_upgraded_email(
        self,
        to_email: str,
        user_name: str,
        plan_name: str,
        amount: str,
        billing_period: str,
        next_charge_date: str,
    ) -> bool:
        """Send subscription upgrade/update email."""
        variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": amount,
            "billing_period": billing_period,
            "next_charge_date": next_charge_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }
        return await self.send_email(
            to_email=to_email,
            subject=f"Subscription Updated - {plan_name.title()} Plan",
            template=EmailTemplate.SUBSCRIPTION_UPGRADED,
            variables=variables,
        )

    async def send_payment_failed_email(
        self,
        to_email: str,
        user_name: str,
        plan_name: str,
        amount: str,
        failed_date: str,
    ) -> bool:
        """Send payment failure notification email."""
        variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": amount,
            "failed_date": failed_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }
        return await self.send_email(
            to_email=to_email,
            subject="Payment Failed - Action Required",
            template=EmailTemplate.PAYMENT_FAILED,
            variables=variables,
        )
