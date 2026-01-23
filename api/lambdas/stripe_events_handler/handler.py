import logging
import os
from typing import Optional

import stripe

from src.config import settings
from src.payments.subscriptions import Subscription, SubscriptionRepository
from src.users import UserRepository
from .models import (
    StripeCheckoutSession,
    StripeEvent,
    StripeInvoice,
    StripePrice,
    StripePriceInfo,
    StripeSubscriptionData,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
log = logging.getLogger(__name__)
log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def _safe_str(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.lower() in {"none", "null", ""}:
        return None
    return str(value)


def _extract_price_info(subscription: StripeSubscriptionData) -> StripePriceInfo:
    price = subscription.first_price()
    if not price:
        return StripePriceInfo()
    metadata = price.metadata or {}
    billing_cycle = metadata.get("billing_cycle")
    if not billing_cycle:
        billing_cycle = "monthly" if (price.recurring or {}).get("interval") == "month" else "annual"
    return StripePriceInfo(
        plan_key=metadata.get("plan_key"),
        billing_cycle=billing_cycle,
        currency=price.currency,
        amount=price.unit_amount,
    )


def _extract_user_email(subscription: StripeSubscriptionData, fallback_customer: Optional[str]) -> Optional[str]:
    metadata = subscription.metadata or {}
    user_email = metadata.get("user_email")
    if user_email:
        return user_email
    if fallback_customer:
        try:
            customer = stripe.Customer.retrieve(fallback_customer)
            return customer.get("email")
        except Exception as exc:
            log.warning("Failed to fetch customer email: %s", exc)
    return None


def _persist_subscription(subscription: StripeSubscriptionData) -> None:
    customer_id = subscription.customer
    price_info = _extract_price_info(subscription)
    user_email = _extract_user_email(subscription, customer_id)
    if not user_email:
        log.warning("Stripe event missing user email; skipping subscription persistence.")
        return

    repo = SubscriptionRepository()
    user_repo = UserRepository()
    existing = user_repo.get_by_email(user_email)
    if existing and customer_id:
        user_repo.update_stripe_customer_id(user_email, customer_id)
    elif not existing:
        from src.users import User
        user_repo.create_or_update(User(email=user_email, name=user_email.split("@")[0], stripe_customer_id=customer_id))

    subscription_record = Subscription(
        subscription_id=subscription.id,
        user_email=user_email,
        customer_id=customer_id,
        status=subscription.status,
        plan_name=price_info.plan_key or subscription.metadata.get("plan_key"),
        price_id=(subscription.first_price() or StripePrice()).id,
        billing_cycle=price_info.billing_cycle,
        current_period_start=_safe_str(subscription.current_period_start),
        current_period_end=_safe_str(subscription.current_period_end),
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=_safe_str(subscription.canceled_at),
        trial_end=_safe_str(subscription.trial_end),
        currency=price_info.currency,
        amount=price_info.amount,
        latest_invoice_id=subscription.latest_invoice,
    )
    log.info("Persisting subscription pk=%s sk=%s status=%s", subscription_record.pk, subscription_record.sk, subscription_record.status)
    repo.upsert(subscription_record)


def handler(event, context):
    log.info("Stripe event received keys=%s", list(event.keys()))
    if not settings.stripe_secret_key:
        log.warning("STRIPE_SECRET_KEY not configured; skipping Stripe event processing.")
        return {"status": "ignored"}
    stripe.api_key = settings.stripe_secret_key

    detail = event.get("detail") or {}
    stripe_event = StripeEvent.model_validate(detail)
    event_type = stripe_event.type
    log.info("Stripe event type=%s", event_type)
    obj = stripe_event.data.object or {}

    if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        subscription = StripeSubscriptionData.model_validate(obj)
        _persist_subscription(subscription)
        log.info("Processed subscription event %s for subscription_id=%s", event_type, subscription.id)
        return {"status": "ok"}

    if event_type == "checkout.session.completed":
        session = StripeCheckoutSession.model_validate(obj)
        subscription_id = session.subscription
        if not subscription_id:
            return {"status": "ignored"}
        try:
            subscription = StripeSubscriptionData.model_validate(
                stripe.Subscription.retrieve(subscription_id)
            )
        except Exception as exc:
            log.warning("Failed to retrieve subscription %s: %s", subscription_id, exc)
            return {"status": "retry"}
        _persist_subscription(subscription)
        log.info("Processed checkout session for subscription_id=%s", subscription_id)
        return {"status": "ok"}

    if event_type == "invoice.paid":
        invoice = StripeInvoice.model_validate(obj)
        subscription_id = invoice.subscription
        if not subscription_id:
            return {"status": "ignored"}
        try:
            subscription = StripeSubscriptionData.model_validate(
                stripe.Subscription.retrieve(subscription_id)
            )
        except Exception as exc:
            log.warning("Failed to retrieve subscription %s: %s", subscription_id, exc)
            return {"status": "retry"}
        _persist_subscription(subscription)
        log.info("Processed invoice.paid for subscription_id=%s", subscription_id)
        return {"status": "ok"}

    return {"status": "ignored"}
