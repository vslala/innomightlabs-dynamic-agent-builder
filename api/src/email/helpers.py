"""Email helper functions to reduce code duplication."""
import logging
from typing import Optional, Dict

from src.config import settings
from src.users import UserRepository
from .service import EmailService
from .pending_email import (
    PendingEmailRepository,
    create_pending_email,
    EmailType,
)

log = logging.getLogger(__name__)


def _handle_email_failure(
    to_email: str,
    email_type: EmailType,
    subject: str,
    template_variables: Dict[str, str],
) -> None:
    """
    Handle email sending failure by creating a pending email for retry.

    Args:
        to_email: Recipient email address
        email_type: Type of email that failed
        subject: Email subject line
        template_variables: Template variables for the email
    """
    log.warning(f"Failed to send {email_type.value} email to {to_email}, creating pending email")

    pending_email_repo = PendingEmailRepository()
    pending_email = create_pending_email(
        to_email=to_email,
        email_type=email_type,
        subject=subject,
        template_variables=template_variables,
    )
    pending_email_repo.create(pending_email)


async def send_welcome_email_safe(user_email: str) -> None:
    """
    Send welcome email with automatic retry on failure.

    Args:
        user_email: New user's email address
    """
    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)
        if not user:
            log.warning(f"Cannot send welcome email: user {user_email} not found")
            return

        email_service = EmailService()
        user_name = user.name or user_email.split("@")[0]
        template_variables = {
            "user_name": user_name,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
        }

        success = await email_service.send_welcome_email(
            to_email=user_email,
            user_name=user_name,
        )

        if success:
            log.info(f"✓ Successfully sent welcome email to {user_email}")
        else:
            _handle_email_failure(
                to_email=user_email,
                email_type=EmailType.WELCOME,
                subject="Welcome to InnomightLabs! 🎉",
                template_variables=template_variables,
            )
    except Exception as e:
        log.error(f"✗ Error sending welcome email to {user_email}: {e}", exc_info=True)


async def send_subscription_confirmed_email_safe(
    user_email: str,
    plan_name: str,
    amount_cents: int,
    currency: str,
    current_period_end: str,
) -> None:
    """
    Send subscription confirmation email with automatic retry on failure.

    Args:
        user_email: Subscriber's email address
        plan_name: Name of the subscription plan
        amount_cents: Amount paid in cents
        currency: Currency code (e.g., 'usd')
        current_period_end: Unix timestamp string for next charge date
    """
    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)
        if not user:
            log.warning(f"Cannot send subscription confirmed email: user {user_email} not found")
            return

        email_service = EmailService()

        # Format amount
        amount_in_dollars = amount_cents / 100
        formatted_amount = f"{currency.upper()} {amount_in_dollars:.2f}"

        # Format next charge date
        from datetime import datetime
        next_charge_date = datetime.fromtimestamp(int(current_period_end)).strftime("%B %d, %Y")

        # Determine billing period
        billing_period = "Monthly" if "month" in plan_name.lower() else "Annual"

        user_name = user.name or user_email.split("@")[0]
        template_variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": formatted_amount,
            "billing_period": billing_period,
            "next_charge_date": next_charge_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }

        success = await email_service.send_subscription_confirmed_email(
            to_email=user_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=formatted_amount,
            billing_period=billing_period,
            next_charge_date=next_charge_date,
        )

        if success:
            log.info(f"✓ Successfully sent subscription confirmed email to {user_email} (plan: {plan_name})")
        else:
            _handle_email_failure(
                to_email=user_email,
                email_type=EmailType.SUBSCRIPTION_CONFIRMED,
                subject=f"Subscription Confirmed - {plan_name.title()} Plan",
                template_variables=template_variables,
            )
    except Exception as e:
        log.error(f"✗ Error sending subscription confirmed email to {user_email}: {e}", exc_info=True)


async def send_payment_failed_email_safe(
    user_email: str,
    plan_name: str,
    amount_cents: int,
    currency: str,
) -> None:
    """
    Send payment failure notification email with automatic retry on failure.

    Args:
        user_email: User's email address
        plan_name: Name of the subscription plan
        amount_cents: Amount that failed to charge in cents
        currency: Currency code (e.g., 'usd')
    """
    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)
        if not user:
            log.warning(f"Cannot send payment failed email: user {user_email} not found")
            return

        email_service = EmailService()

        # Format amount
        amount_in_dollars = amount_cents / 100
        formatted_amount = f"{currency.upper()} {amount_in_dollars:.2f}"

        # Format failed date
        from datetime import datetime
        failed_date = datetime.now().strftime("%B %d, %Y")

        user_name = user.name or user_email.split("@")[0]
        template_variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": formatted_amount,
            "failed_date": failed_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }

        success = await email_service.send_payment_failed_email(
            to_email=user_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=formatted_amount,
            failed_date=failed_date,
        )

        if success:
            log.info(f"✓ Successfully sent payment failed email to {user_email} (plan: {plan_name}, amount: {formatted_amount})")
        else:
            _handle_email_failure(
                to_email=user_email,
                email_type=EmailType.PAYMENT_FAILED,
                subject="Payment Failed - Action Required",
                template_variables=template_variables,
            )
    except Exception as e:
        log.error(f"✗ Error sending payment failed email to {user_email}: {e}", exc_info=True)


async def send_subscription_upgraded_email_safe(
    user_email: str,
    plan_name: str,
    amount_cents: int,
    currency: str,
    current_period_end: str,
) -> None:
    """
    Send subscription upgrade/update email with automatic retry on failure.

    Args:
        user_email: User's email address
        plan_name: Name of the new/updated subscription plan
        amount_cents: Amount in cents
        currency: Currency code (e.g., 'usd')
        current_period_end: Unix timestamp string for next charge date
    """
    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)
        if not user:
            log.warning(f"Cannot send subscription upgraded email: user {user_email} not found")
            return

        email_service = EmailService()

        # Format amount
        amount_in_dollars = amount_cents / 100
        formatted_amount = f"{currency.upper()} {amount_in_dollars:.2f}"

        # Format next charge date
        from datetime import datetime
        next_charge_date = datetime.fromtimestamp(int(current_period_end)).strftime("%B %d, %Y")

        # Determine billing period
        billing_period = "Monthly" if "month" in plan_name.lower() else "Annual"

        user_name = user.name or user_email.split("@")[0]
        template_variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "amount": formatted_amount,
            "billing_period": billing_period,
            "next_charge_date": next_charge_date,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }

        success = await email_service.send_subscription_upgraded_email(
            to_email=user_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=formatted_amount,
            billing_period=billing_period,
            next_charge_date=next_charge_date,
        )

        if success:
            log.info(f"✓ Successfully sent subscription upgraded email to {user_email} (new plan: {plan_name})")
        else:
            _handle_email_failure(
                to_email=user_email,
                email_type=EmailType.SUBSCRIPTION_UPGRADED,
                subject=f"Subscription Updated - {plan_name.title()} Plan",
                template_variables=template_variables,
            )
    except Exception as e:
        log.error(f"✗ Error sending subscription upgraded email to {user_email}: {e}", exc_info=True)


async def send_subscription_cancelled_email_safe(
    user_email: str,
    plan_name: str,
    current_period_end: str,
) -> None:
    """
    Send subscription cancellation email with automatic retry on failure.

    Args:
        user_email: User's email address
        plan_name: Name of the cancelled subscription plan
        current_period_end: Unix timestamp string for when access ends
    """
    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)
        if not user:
            log.warning(f"Cannot send subscription cancelled email: user {user_email} not found")
            return

        email_service = EmailService()

        # Format access until date
        from datetime import datetime
        access_until = datetime.fromtimestamp(int(current_period_end)).strftime("%B %d, %Y")

        user_name = user.name or user_email.split("@")[0]
        template_variables = {
            "user_name": user_name,
            "plan_name": plan_name.title(),
            "access_until": access_until,
            "dashboard_url": f"{settings.frontend_url}/dashboard",
            "settings_url": f"{settings.frontend_url}/dashboard/settings",
        }

        success = await email_service.send_subscription_cancelled_email(
            to_email=user_email,
            user_name=user_name,
            plan_name=plan_name,
            access_until=access_until,
        )

        if success:
            log.info(f"✓ Successfully sent subscription cancelled email to {user_email} (plan: {plan_name}, access until: {access_until})")
        else:
            _handle_email_failure(
                to_email=user_email,
                email_type=EmailType.SUBSCRIPTION_CANCELLED,
                subject="Subscription Cancelled",
                template_variables=template_variables,
            )
    except Exception as e:
        log.error(f"✗ Error sending subscription cancelled email to {user_email}: {e}", exc_info=True)
