"""Stripe payments integration - optimized for correct webhook event handling."""

import json
import logging
from typing import Optional

import httpx
import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.payments.stripe.models import (
    CheckoutRequest,
    CheckoutResponse,
    InvoicePeriod,
    PriceInfo,
    PricingFaq,
    PricingResponse,
    PricingTier,
    SessionAuthResponse,
    SubscriptionMetadata,
    SubscriptionStatusResponse,
)

from ...config import settings
from ..pricing_config import get_pricing_config
from ...users import User, UserRepository
from ..subscriptions import Subscription, SubscriptionRepository
from ...email import (
    send_subscription_confirmed_email_safe,
    send_payment_failed_email_safe,
    send_subscription_upgraded_email_safe,
    send_subscription_cancelled_email_safe,
)
from ..subscriptions.repository import WebhookEventRepository
from ...auth.jwt_utils import create_access_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/stripe", tags=["payments"])


# ============================================================================
# Stripe API Client
# ============================================================================

class StripeClient:
    BASE_URL = "https://api.stripe.com/v1"
    
    def __init__(self):
        if not settings.stripe_secret_key:
            raise HTTPException(500, "Stripe not configured")
        self.headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}
    
    async def _request(self, method: str, path: str, data: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            kwargs = {"headers": self.headers}
            if data:
                kwargs["data"] = data
            
            response = await getattr(client, method)(f"{self.BASE_URL}{path}", **kwargs)
            
            if response.status_code >= 400:
                log.error(f"Stripe API error {response.status_code}: {response.text}")
                raise HTTPException(502, "Stripe API request failed")
            
            return response.json()
    
    async def get(self, path: str) -> dict:
        return await self._request("get", path)
    
    async def post(self, path: str, data: dict) -> dict:
        return await self._request("post", path, data)

# ============================================================================
# Utilities
# ============================================================================

def get_price_id(plan_key: str, billing_cycle: str) -> str:
    """Get Stripe price ID for plan and billing cycle."""
    config = get_pricing_config()
    for tier in config.tiers:
        if tier.key == plan_key:
            return tier.stripe_price_ids.get(billing_cycle, "")
    return ""

def normalize_value(value: Optional[object]) -> Optional[str]:
    """Normalize value to string or None."""
    if value is None or (isinstance(value, str) and value.lower() in {"none", "null", ""}):
        return None
    return str(value)

def ensure_user_exists(email: str, customer_id: Optional[str] = None) -> None:
    """Create user if doesn't exist, update customer_id if provided."""
    repo = UserRepository()
    user = repo.get_by_email(email)
    
    if user:
        if customer_id:
            repo.update_stripe_customer_id(email, customer_id)
    else:
        new_user = User(email=email, name=email.split("@")[0], stripe_customer_id=customer_id)
        repo.create_or_update(new_user)

def extract_subscription_metadata(stripe_sub: dict) -> SubscriptionMetadata:
    """Extract plan_key and billing_cycle from Stripe subscription metadata."""
    metadata = stripe_sub.get("metadata", {})
    return SubscriptionMetadata(
        plan_key=metadata.get("plan_key", "free"),
        billing_cycle=metadata.get("billing_cycle", "monthly"),
    )

def extract_price_info(stripe_data: dict) -> PriceInfo:
    """Extract price_id, currency, amount from Stripe data."""
    items = stripe_data.get("items", {}).get("data", [])
    if not items:
        return PriceInfo()
    
    price = items[0].get("price", {}) or {}
    return PriceInfo(
        price_id=price.get("id"),
        currency=price.get("currency"),
        amount=price.get("unit_amount"),
    )

def extract_invoice_period(invoice_data: dict) -> InvoicePeriod:
    """Extract period start/end from invoice line items if present."""
    lines = invoice_data.get("lines", {}).get("data", [])
    if not lines:
        return InvoicePeriod()
    period = (lines[0] or {}).get("period", {}) or {}
    return InvoicePeriod(
        start=normalize_value(period.get("start")),
        end=normalize_value(period.get("end")),
    )

def create_subscription_from_stripe(
    stripe_sub: dict,
    subscription_id: str,
    customer_email: str,
    customer_id: str,
) -> Subscription:
    """Create Subscription object from Stripe subscription data."""
    metadata = extract_subscription_metadata(stripe_sub)
    price_info = extract_price_info(stripe_sub)
    
    return Subscription(
        subscription_id=subscription_id,
        user_email=customer_email,
        customer_id=customer_id,
        status=stripe_sub.get("status"),
        plan_name=metadata.plan_key,
        price_id=price_info.price_id,
        billing_cycle=metadata.billing_cycle,
        current_period_start=normalize_value(stripe_sub.get("current_period_start")),
        current_period_end=normalize_value(stripe_sub.get("current_period_end")),
        cancel_at_period_end=stripe_sub.get("cancel_at_period_end"),
        canceled_at=normalize_value(stripe_sub.get("canceled_at")),
        trial_end=normalize_value(stripe_sub.get("trial_end")),
        currency=price_info.currency,
        amount=price_info.amount,
        latest_invoice_id=stripe_sub.get("latest_invoice"),
    )

async def get_customer_email(customer_id: str) -> Optional[str]:
    """Get customer email from Stripe, returns None if not found."""
    stripe = StripeClient()
    customer = await stripe.get(f"/customers/{customer_id}")
    email = customer.get("email")
    if not email:
        log.error(f"No email for customer {customer_id}")
    return email

async def sync_subscription_to_db(
    subscription_data: dict,
    subscription_id: str,
    customer_id: str,
    invoice_data: Optional[dict] = None,
) -> Optional[Subscription]:
    """
    Sync Stripe subscription to database.
    Ensures user exists, extracts invoice periods, and upserts subscription.
    """
    log.info(f"Syncing subscription {subscription_id} to database")

    customer_email = await get_customer_email(customer_id)
    if not customer_email:
        log.error(f"Cannot sync subscription {subscription_id}: no customer email for {customer_id}")
        return None

    log.info(f"Customer email: {customer_email}")

    ensure_user_exists(customer_email, customer_id)

    subscription = create_subscription_from_stripe(
        subscription_data, subscription_id, customer_email, customer_id
    )

    log.info(f"Created subscription object: plan={subscription.plan_name}, status={subscription.status}")

    if invoice_data:
        period = extract_invoice_period(invoice_data)
        if period.start or period.end:
            subscription.current_period_start = period.start or subscription.current_period_start
            subscription.current_period_end = period.end or subscription.current_period_end
            log.info(f"Extracted period: start={period.start}, end={period.end}")

    SubscriptionRepository().upsert(subscription)
    log.info(f"✓ Subscription {subscription_id} synced to database successfully")
    return subscription

async def get_active_stripe_subscription(customer_id: str) -> Optional[SubscriptionStatusResponse]:
    """Fetch active Stripe subscription for a customer_id and map to status response."""
    stripe = StripeClient()
    subscriptions_response = await stripe.get(
        f"/subscriptions?customer={customer_id}&status=active&limit=1"
    )
    subscriptions = subscriptions_response.get("data", [])
    if not subscriptions:
        return None
    stripe_sub = subscriptions[0]
    metadata = extract_subscription_metadata(stripe_sub)

    # Extract period dates from subscription items (Stripe's new structure)
    period_start = None
    period_end = None
    items = stripe_sub.get("items", {}).get("data", [])
    if items:
        period_start = items[0].get("current_period_start")
        period_end = items[0].get("current_period_end")

    return SubscriptionStatusResponse(
        tier=metadata.plan_key or "free",
        status=stripe_sub.get("status"),
        current_period_start=normalize_value(period_start),
        current_period_end=normalize_value(period_end),
        is_active=True,
        cancel_at_period_end=stripe_sub.get("cancel_at_period_end"),
    )


def validate_checkout_request(user_email: str, plan_key: str) -> Optional[str]:
    """
    Validate checkout request against existing subscriptions.

    Rules:
    - Block if user already has same plan active
    - Block downgrades (direct to Settings for subscription modification)
    - Allow upgrades to higher tiers
    - Allow if no active subscription

    Returns:
        Error message if validation fails, None if valid.
    """
    repo = SubscriptionRepository()
    active_sub = repo.get_active_for_user(user_email)

    if not active_sub:
        return None  # No active subscription, allow checkout

    current_plan = active_sub.plan_name

    # Block same plan purchase
    if current_plan == plan_key:
        return (
            f"You already have an active {plan_key} subscription. "
            f"Visit Settings to manage your subscription."
        )

    # Define tier hierarchy
    tier_order = {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}
    current_tier = tier_order.get(current_plan, 0)
    requested_tier = tier_order.get(plan_key, 0)

    # Block downgrades
    if requested_tier < current_tier:
        return (
            f"To downgrade from {current_plan} to {plan_key}, "
            f"please visit Settings → Manage Subscription to modify your plan. "
            f"Your {current_plan} plan will continue until the end of your billing period."
        )

    # Allow upgrades (higher tier)
    return None

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/pricing", response_model=PricingResponse)
async def get_pricing():
    """Get pricing tiers and FAQs."""
    config = get_pricing_config()
    
    tiers = [
        PricingTier(
            name=t.name, badge=t.badge, description=t.description, prices=t.prices,
            planKey=t.key if t.stripe_price_ids else None, ctaLabel=t.cta.label,
            ctaHref=t.cta.href, highlighted=t.highlighted, features=t.features
        )
        for t in config.tiers
    ]
    
    faqs = [
        PricingFaq(question="Do annual plans include a discount?",
                   answer="Yes. Annual billing saves 17%, equivalent to two months free."),
        PricingFaq(question="Can I change plans later?",
                   answer="Absolutely. Upgrade or downgrade anytime from your dashboard."),
        PricingFaq(question="What happens if I exceed my limits?",
                   answer="You'll be prompted to upgrade. No overages - your usage is capped at your plan limits."),
    ]
    
    return PricingResponse(tiers=tiers, faqs=faqs)

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(payload: CheckoutRequest, request: Request):
    """Create Stripe checkout session with validation."""
    stripe = StripeClient()

    # Extract authenticated user email from middleware
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in to continue."
        )

    # Validate against existing subscriptions
    validation_error = validate_checkout_request(user_email, payload.planKey)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    # Get price ID from config
    price_id = get_price_id(payload.planKey, payload.billingCycle)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Plan '{payload.planKey}' with '{payload.billingCycle}' billing not found in pricing config"
        )

    # Create Stripe session with authenticated email
    session_data = {
        "mode": "subscription",
        "success_url": f"{settings.frontend_url}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.frontend_url}/payments/cancel",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "allow_promotion_codes": "true",
        "customer_email": user_email,  # Use authenticated email
        "subscription_data[metadata][plan_key]": payload.planKey,
        "subscription_data[metadata][billing_cycle]": payload.billingCycle,
        "subscription_data[metadata][user_email]": user_email,  # Store in metadata for webhook
    }

    response = await stripe.post("/checkout/sessions", session_data)
    return CheckoutResponse(url=response["url"])

@router.get("/session/{session_id}", response_model=SessionAuthResponse)
async def exchange_session_for_auth(session_id: str):
    """Exchange Stripe session ID for JWT token after successful payment."""
    stripe = StripeClient()
    
    # Fetch and validate session
    try:
        session = await stripe.get(f"/checkout/sessions/{session_id}")
    except HTTPException:
        raise HTTPException(404, "Session not found or expired")
    
    if session.get("payment_status") != "paid":
        raise HTTPException(400, f"Payment not completed. Status: {session.get('payment_status')}")
    
    # Get customer email
    customer_email = session.get("customer_details", {}).get("email")
    if not customer_email and (customer_id := session.get("customer")):
        customer = await stripe.get(f"/customers/{customer_id}")
        customer_email = customer.get("email")
    
    if not customer_email:
        raise HTTPException(400, "No email found in session")
    
    # Create/get user
    ensure_user_exists(customer_email, customer_id=session.get("customer"))
    user = UserRepository().get_by_email(customer_email)
    
    if not user:
        raise HTTPException(500, "Failed to create user")
    
    # Generate JWT and check subscription
    jwt_token = create_access_token(user)
    subscription = SubscriptionRepository().get_active_for_user(customer_email)
    
    return SessionAuthResponse(
        token=jwt_token,
        email=customer_email,
        subscription_status=subscription.status if subscription else None,
    )

@router.get("/subscription/status")
async def get_subscription_status(request: Request):
    """Get current subscription status for authenticated user."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(401, "Not authenticated")

    subscription = SubscriptionRepository().get_active_for_user(user_email)

    if subscription:
        return SubscriptionStatusResponse(
            tier=subscription.plan_name or "free",
            status=subscription.status,
            current_period_start=normalize_value(subscription.current_period_start),
            current_period_end=normalize_value(subscription.current_period_end),
            is_active=True,
            cancel_at_period_end=subscription.cancel_at_period_end,
        )

    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)

        customer_id = user.stripe_customer_id if user else None
        if customer_id:
            stripe_subscription = await get_active_stripe_subscription(customer_id)
            if stripe_subscription:
                return stripe_subscription
    except Exception as e:
        log.warning(f"Stripe fallback failed for {user_email}: {e}")

    return SubscriptionStatusResponse(
        tier="free",
        status=None,
        current_period_start=None,
        current_period_end=None,
        is_active=False,
    )

@router.post("/subscription/cancel")
async def cancel_subscription(request: Request):
    """Cancel subscription at the end of the current billing period."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(401, "Not authenticated")

    # Get active subscription from database
    repo = SubscriptionRepository()
    subscription = repo.get_active_for_user(user_email)
    if not subscription:
        raise HTTPException(
            404,
            "No active subscription found. If you just signed up, please wait 30 seconds for processing.",
        )

    if subscription.user_email != user_email:
        log.error(f"Subscription ownership mismatch: {subscription.subscription_id} vs {user_email}")
        raise HTTPException(403, "Unauthorized")

    # Check if already scheduled for cancellation (from DB)
    if subscription and subscription.cancel_at_period_end:
        raise HTTPException(400, "Subscription is already scheduled for cancellation")

    try:
        stripe = StripeClient()

        # Update subscription to cancel at period end
        update_response = await stripe.post(
            f"/subscriptions/{subscription.subscription_id}",
            {"cancel_at_period_end": "true"}
        )

        # Log what we got from Stripe for debugging
        log.info(f"Stripe cancel response - current_period_end: {update_response.get('current_period_end')}, "
                f"cancel_at_period_end: {update_response.get('cancel_at_period_end')}, "
                f"canceled_at: {update_response.get('canceled_at')}")

        subscription.cancel_at_period_end = True
        subscription.canceled_at = normalize_value(update_response.get("canceled_at"))
        subscription.current_period_end = normalize_value(update_response.get("current_period_end"))
        repo.upsert(subscription)

        return {
            "success": True,
            "message": "Subscription will be cancelled at the end of the current billing period",
            "current_period_end": normalize_value(update_response.get("current_period_end"))
        }

    except Exception as e:
        log.error(f"Failed to cancel subscription for {user_email}: {e}")
        raise HTTPException(500, "Failed to cancel subscription")

# ============================================================================
# Webhook Handler
# ============================================================================

@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handle Stripe webhooks for subscription lifecycle events.

    Key events processed:
    - invoice.payment_succeeded / invoice.paid: Payment successful → activate subscription
    - invoice.payment_failed: Payment failed → notify/retry
    - customer.subscription.updated: Subscription changed → update DB
    - customer.subscription.deleted: Subscription cancelled → revoke access
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    if not sig:
        log.error("Missing stripe-signature header")
        raise HTTPException(400, "Missing stripe-signature header")

    if not settings.stripe_webhook_secret:
        log.error("Stripe webhook secret not configured in environment")
        raise HTTPException(500, "Webhook secret not configured")

    # Use Stripe's construct_event for signature verification + parsing
    try:
        webhook_event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig,
            secret=settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError as e:
        log.error(
            f"Webhook signature verification failed: {e}. "
            f"Payload length: {len(payload)} bytes, "
            f"Signature header: {sig[:50]}..., "
            f"Secret configured: {bool(settings.stripe_webhook_secret)}, "
            f"Secret length: {len(settings.stripe_webhook_secret) if settings.stripe_webhook_secret else 0}"
        )
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        log.error(f"Error constructing webhook event: {e}", exc_info=True)
        raise HTTPException(400, "Invalid webhook event")

    log.debug("Webhook payload: %s", json.dumps(dict(webhook_event), indent=2, default=str))

    event_id = webhook_event.id
    event_type = webhook_event.type

    # Check deduplication BEFORE processing
    if event_id:
        webhook_repo = WebhookEventRepository()
        if webhook_repo.has_processed(event_id):
            log.info(f"Webhook event {event_id} already processed, skipping")
            return {"status": "ok"}

    data = webhook_event.data.object

    log.info(f"Processing webhook: {event_type} (event_id: {event_id})")

    # Route to appropriate handler - wrap in try-catch to ensure we only mark as processed if successful
    try:
        if event_type in ("invoice.payment_succeeded", "invoice.paid", "invoice_payment.paid"):
            await handle_invoice_payment_succeeded(data)
        elif event_type == "invoice.payment_failed":
            await handle_invoice_payment_failed(data)
        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(data)
        else:
            log.info(f"Unhandled event type: {event_type}")

        # ONLY mark as processed if handler succeeded without exception
        if event_id:
            webhook_repo = WebhookEventRepository()
            webhook_repo.mark_processed(event_id)
            log.info(f"✓ Successfully processed webhook event {event_id} ({event_type})")

        return {"status": "ok"}

    except Exception as e:
        # Log error but don't mark as processed - Stripe will retry
        log.error(f"✗ Failed to process webhook event {event_id} ({event_type}): {e}", exc_info=True)
        # Re-raise so Stripe knows to retry
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")

# ============================================================================
# Webhook Event Handlers
# ============================================================================

async def handle_invoice_payment_succeeded(invoice_data: dict) -> None:
    """
    Handle successful payment - this is the PRIMARY event for activating subscriptions.

    Event flow:
    1. Customer completes checkout
    2. Stripe charges card
    3. invoice.payment_succeeded (or invoice.paid) fires → WE ARE HERE
    4. We create/update subscription in DB with status 'active'

    Note: Handles both 'invoice.payment_succeeded' and 'invoice.paid' events
    Also handles 'invoice_payment' objects by fetching the actual invoice
    """
    # Check if this is an invoice_payment object (needs to fetch the invoice)
    if invoice_data.get("object") == "invoice_payment":
        invoice_id = invoice_data.get("invoice")
        if not invoice_id:
            log.warning("invoice_payment object missing invoice reference")
            return

        log.info(f"Fetching invoice {invoice_id} from invoice_payment event")
        stripe = StripeClient()
        invoice_data = await stripe.get(f"/invoices/{invoice_id}")

    # Extract subscription_id - handle both old and new Stripe API structures
    # Old API: invoice.subscription (direct)
    # New API (2025-12-15+): invoice.parent.subscription_details.subscription (nested)
    subscription_id = invoice_data.get("subscription")
    if not subscription_id:
        parent = invoice_data.get("parent", {})
        if parent.get("type") == "subscription_details":
            subscription_details = parent.get("subscription_details", {})
            subscription_id = subscription_details.get("subscription")

    customer_id = invoice_data.get("customer")

    if not subscription_id or not customer_id:
        log.warning(
            f"Invoice data missing subscription or customer: {invoice_data.get('id')} "
            f"(subscription={subscription_id}, customer={customer_id})"
        )
        return

    # Fetch full subscription details
    stripe = StripeClient()
    stripe_sub = await stripe.get(f"/subscriptions/{subscription_id}")
    
    subscription = await sync_subscription_to_db(
        stripe_sub,
        subscription_id,
        customer_id,
        invoice_data=invoice_data,
    )
    if not subscription:
        return

    log.info(f"✓ Payment succeeded - activated subscription {subscription_id} for {subscription.user_email}")

    # Send subscription confirmed email
    await send_subscription_confirmed_email_safe(
        user_email=subscription.user_email,
        plan_name=subscription.plan_name,
        amount_cents=invoice_data.get("amount_paid", 0),
        currency=invoice_data.get("currency", "usd"),
        current_period_end=subscription.current_period_end,
    )

async def handle_invoice_payment_failed(invoice_data: dict) -> None:
    """
    Handle failed payment - update subscription status and trigger retry logic.

    This fires when:
    - Initial payment fails (subscription stays in 'incomplete')
    - Renewal payment fails (subscription goes to 'past_due')
    """
    # Check if this is an invoice_payment object (needs to fetch the invoice)
    if invoice_data.get("object") == "invoice_payment":
        invoice_id = invoice_data.get("invoice")
        if not invoice_id:
            log.warning("invoice_payment object missing invoice reference")
            return

        log.info(f"Fetching invoice {invoice_id} from invoice_payment event")
        stripe = StripeClient()
        invoice_data = await stripe.get(f"/invoices/{invoice_id}")

    # Extract subscription_id - handle both old and new Stripe API structures
    # Old API: invoice.subscription (direct)
    # New API (2025-12-15+): invoice.parent.subscription_details.subscription (nested)
    subscription_id = invoice_data.get("subscription")
    if not subscription_id:
        parent = invoice_data.get("parent", {})
        if parent.get("type") == "subscription_details":
            subscription_details = parent.get("subscription_details", {})
            subscription_id = subscription_details.get("subscription")

    customer_id = invoice_data.get("customer")
    attempt_count = invoice_data.get("attempt_count", 0)

    if not subscription_id or not customer_id:
        log.warning(
            f"invoice.payment_failed missing subscription or customer: {invoice_data.get('id')} "
            f"(subscription={subscription_id}, customer={customer_id})"
        )
        return

    stripe = StripeClient()

    # Fetch subscription to get current status
    stripe_sub = await stripe.get(f"/subscriptions/{subscription_id}")

    subscription = await sync_subscription_to_db(
        stripe_sub,
        subscription_id,
        customer_id,
        invoice_data=invoice_data,
    )
    if not subscription:
        return

    log.warning(
        f"✗ Payment failed (attempt {attempt_count}) - subscription {subscription_id} "
        f"for {subscription.user_email} status: {subscription.status}"
    )

    # Send payment failed email
    await send_payment_failed_email_safe(
        user_email=subscription.user_email,
        plan_name=subscription.plan_name,
        amount_cents=invoice_data.get("amount_due", 0),
        currency=invoice_data.get("currency", "usd"),
    )

async def handle_subscription_updated(subscription_data: dict) -> None:
    """
    Handle subscription updates - plan changes, cancellations scheduled, etc.
    
    This fires when:
    - User upgrades/downgrades plan
    - cancel_at_period_end is set
    - Subscription status changes
    """
    subscription_id = subscription_data.get("id")
    customer_id = subscription_data.get("customer")
    
    if not subscription_id or not customer_id:
        log.warning("customer.subscription.updated missing id or customer")
        return

    subscription = await sync_subscription_to_db(
        subscription_data, subscription_id, customer_id
    )
    if not subscription:
        return

    log.info(
        f"↻ Subscription updated {subscription_id} for {subscription.user_email} - status: {subscription.status}"
    )

    # Send subscription upgraded email (only for plan changes, not cancellations)
    if not subscription_data.get("cancel_at_period_end"):
        # Get latest invoice to get amount
        stripe = StripeClient()
        try:
            latest_invoice_id = subscription_data.get("latest_invoice")
            if latest_invoice_id:
                invoice = await stripe.get(f"/invoices/{latest_invoice_id}")
                amount_cents = invoice.get("amount_paid", 0)
                currency = invoice.get("currency", "usd")

                await send_subscription_upgraded_email_safe(
                    user_email=subscription.user_email,
                    plan_name=subscription.plan_name,
                    amount_cents=amount_cents,
                    currency=currency,
                    current_period_end=subscription.current_period_end,
                )
        except Exception as e:
            log.warning(f"Could not send subscription upgraded email (missing invoice): {e}")

async def handle_subscription_deleted(subscription_data: dict) -> None:
    """
    Handle subscription deletion - revoke access.
    
    This fires when:
    - Subscription is cancelled and deleted immediately
    - Subscription ends after cancel_at_period_end period expires
    """
    subscription_id = subscription_data.get("id")
    customer_id = subscription_data.get("customer")
    
    if not subscription_id or not customer_id:
        log.warning("customer.subscription.deleted missing id or customer")
        return

    subscription = await sync_subscription_to_db(
        subscription_data, subscription_id, customer_id
    )
    if not subscription:
        return

    log.info(f"✗ Subscription deleted {subscription_id} for {subscription.user_email}")

    # Send subscription cancelled email
    await send_subscription_cancelled_email_safe(
        user_email=subscription.user_email,
        plan_name=subscription.plan_name,
        current_period_end=subscription.current_period_end,
    )
