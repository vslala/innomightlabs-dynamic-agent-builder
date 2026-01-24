"""Stripe payments integration - optimized for correct webhook event handling."""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.payments.stripe.models import (
    CheckoutRequest,
    CheckoutResponse,
    PricingFaq,
    PricingResponse,
    PricingTier,
    SessionAuthResponse,
    SubscriptionStatusResponse,
)

from ...config import settings
from ..pricing_config import get_pricing_config
from ...users import User, UserRepository
from ..subscriptions import Subscription, SubscriptionRepository
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

def extract_subscription_metadata(stripe_sub: dict) -> tuple[str, str]:
    """Extract (plan_key, billing_cycle) from Stripe subscription metadata."""
    metadata = stripe_sub.get("metadata", {})
    return metadata.get("plan_key", "free"), metadata.get("billing_cycle", "monthly")

def extract_price_info(stripe_data: dict) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Extract (price_id, currency, amount) from Stripe data."""
    items = stripe_data.get("items", {}).get("data", [])
    if not items:
        return None, None, None
    
    price = items[0].get("price", {}) or {}
    return price.get("id"), price.get("currency"), price.get("unit_amount")

def create_subscription_from_stripe(
    stripe_sub: dict,
    subscription_id: str,
    customer_email: str,
    customer_id: str,
) -> Subscription:
    """Create Subscription object from Stripe subscription data."""
    plan_key, billing_cycle = extract_subscription_metadata(stripe_sub)
    price_id, currency, amount = extract_price_info(stripe_sub)
    
    return Subscription(
        subscription_id=subscription_id,
        user_email=customer_email,
        customer_id=customer_id,
        status=stripe_sub.get("status"),
        plan_name=plan_key,
        price_id=price_id,
        billing_cycle=billing_cycle,
        current_period_start=normalize_value(stripe_sub.get("current_period_start")),
        current_period_end=normalize_value(stripe_sub.get("current_period_end")),
        cancel_at_period_end=stripe_sub.get("cancel_at_period_end"),
        canceled_at=normalize_value(stripe_sub.get("canceled_at")),
        trial_end=normalize_value(stripe_sub.get("trial_end")),
        currency=currency,
        amount=amount,
        latest_invoice_id=stripe_sub.get("latest_invoice"),
    )

def verify_webhook_signature(payload: bytes, signature_header: str) -> None:
    """Verify Stripe webhook signature."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(500, "Webhook secret not configured")
    
    if not signature_header:
        raise HTTPException(400, "Missing stripe-signature header")
    
    # Parse signature
    parts = dict(item.partition("=")[::2] for item in signature_header.split(","))
    timestamp, signatures = parts.get("t"), [v for k, v in parts.items() if k == "v1"]
    
    if not timestamp or not signatures:
        raise HTTPException(400, "Invalid signature header format")
    
    # Verify signature
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected_sig = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    
    if not any(hmac.compare_digest(expected_sig, sig) for sig in signatures):
        raise HTTPException(400, "Invalid signature")
    
    # Check timestamp (5 min tolerance)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(400, "Signature timestamp too old")
    except ValueError:
        raise HTTPException(400, "Invalid timestamp in signature")

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
            current_period_end=normalize_value(subscription.current_period_end),
            is_active=True,
        )

    # Fallback: Check Stripe directly if no subscription in DB (webhook may not have fired yet)
    try:
        stripe = StripeClient()
        user_repo = UserRepository()
        user = user_repo.get_by_email(user_email)

        customer_id = user.stripe_customer_id if user else None

        # If no customer_id stored, search for customer by email
        if not customer_id:
            customers_response = await stripe.get(f"/customers?email={user_email}&limit=1")
            customers = customers_response.get("data", [])
            if customers:
                customer_id = customers[0].get("id")
                # Update user record with customer_id
                if user and customer_id:
                    user_repo.update_stripe_customer_id(user_email, customer_id)

        # Search for active subscriptions
        if customer_id:
            subscriptions_response = await stripe.get(
                f"/subscriptions?customer={customer_id}&status=active&limit=1"
            )

            subscriptions = subscriptions_response.get("data", [])
            if subscriptions:
                stripe_sub = subscriptions[0]
                plan_key, _ = extract_subscription_metadata(stripe_sub)

                # Return the Stripe subscription data
                return SubscriptionStatusResponse(
                    tier=plan_key or "free",
                    status=stripe_sub.get("status"),
                    current_period_end=normalize_value(stripe_sub.get("current_period_end")),
                    is_active=True,
                )
    except Exception as e:
        log.warning(f"Failed to fetch subscription from Stripe for {user_email}: {e}")

    return SubscriptionStatusResponse(tier="free", status=None, current_period_end=None, is_active=False)

# ============================================================================
# Webhook Handler
# ============================================================================

@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handle Stripe webhooks for subscription lifecycle events.
    
    Key events processed:
    - invoice.payment_succeeded: Payment successful → activate subscription
    - invoice.payment_failed: Payment failed → notify/retry
    - customer.subscription.updated: Subscription changed → update DB
    - customer.subscription.deleted: Subscription cancelled → revoke access
    """
    payload = await request.body()
    verify_webhook_signature(payload, request.headers.get("stripe-signature", ""))
    
    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    
    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    
    log.info(f"Webhook received: {event_type}")
    
    # Route to appropriate handler
    if event_type == "invoice.payment_succeeded":
        await handle_invoice_payment_succeeded(data)
    elif event_type == "invoice.payment_failed":
        await handle_invoice_payment_failed(data)
    elif event_type == "customer.subscription.updated":
        await handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(data)
    else:
        log.info(f"Unhandled event type: {event_type}")
    
    return {"status": "ok"}

# ============================================================================
# Webhook Event Handlers
# ============================================================================

async def handle_invoice_payment_succeeded(invoice_data: dict) -> None:
    """
    Handle successful payment - this is the PRIMARY event for activating subscriptions.
    
    Event flow:
    1. Customer completes checkout
    2. Stripe charges card
    3. invoice.payment_succeeded fires → WE ARE HERE
    4. We create/update subscription in DB with status 'active'
    """
    subscription_id = invoice_data.get("subscription")
    customer_id = invoice_data.get("customer")
    
    if not subscription_id or not customer_id:
        log.warning("invoice.payment_succeeded missing subscription or customer")
        return
    
    stripe = StripeClient()
    
    # Get customer email
    customer = await stripe.get(f"/customers/{customer_id}")
    customer_email = customer.get("email")
    
    if not customer_email:
        log.error(f"No email for customer {customer_id}")
        return
    
    # Fetch full subscription details
    stripe_sub = await stripe.get(f"/subscriptions/{subscription_id}")
    
    # Create subscription record
    subscription = create_subscription_from_stripe(
        stripe_sub, subscription_id, customer_email, customer_id
    )
    
    # Ensure user exists and save subscription
    ensure_user_exists(customer_email, customer_id)
    SubscriptionRepository().upsert(subscription)
    
    log.info(f"✓ Payment succeeded - activated subscription {subscription_id} for {customer_email}")

async def handle_invoice_payment_failed(invoice_data: dict) -> None:
    """
    Handle failed payment - update subscription status and trigger retry logic.
    
    This fires when:
    - Initial payment fails (subscription stays in 'incomplete')
    - Renewal payment fails (subscription goes to 'past_due')
    """
    subscription_id = invoice_data.get("subscription")
    customer_id = invoice_data.get("customer")
    attempt_count = invoice_data.get("attempt_count", 0)
    
    if not subscription_id or not customer_id:
        log.warning("invoice.payment_failed missing subscription or customer")
        return
    
    stripe = StripeClient()
    
    # Get customer email
    customer = await stripe.get(f"/customers/{customer_id}")
    customer_email = customer.get("email")
    
    if not customer_email:
        log.error(f"No email for customer {customer_id}")
        return
    
    # Fetch subscription to get current status
    stripe_sub = await stripe.get(f"/subscriptions/{subscription_id}")
    
    # Update subscription with failed status
    subscription = create_subscription_from_stripe(
        stripe_sub, subscription_id, customer_email, customer_id
    )
    
    SubscriptionRepository().upsert(subscription)
    
    log.warning(
        f"✗ Payment failed (attempt {attempt_count}) - subscription {subscription_id} "
        f"for {customer_email} status: {subscription.status}"
    )
    
    # TODO: Send email notification to customer
    # TODO: Implement custom retry logic if needed

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
    
    stripe = StripeClient()
    
    # Get customer email
    customer = await stripe.get(f"/customers/{customer_id}")
    customer_email = customer.get("email")
    
    if not customer_email:
        log.error(f"No email for customer {customer_id}")
        return
    
    # Create subscription record
    subscription = create_subscription_from_stripe(
        subscription_data, subscription_id, customer_email, customer_id
    )
    
    SubscriptionRepository().upsert(subscription)
    
    log.info(f"↻ Subscription updated {subscription_id} for {customer_email} - status: {subscription.status}")

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
    
    stripe = StripeClient()
    
    # Get customer email
    customer = await stripe.get(f"/customers/{customer_id}")
    customer_email = customer.get("email")
    
    if not customer_email:
        log.error(f"No email for customer {customer_id}")
        return
    
    # Mark subscription as cancelled in DB
    subscription = create_subscription_from_stripe(
        subscription_data, subscription_id, customer_email, customer_id
    )
    
    SubscriptionRepository().upsert(subscription)
    
    log.info(f"✗ Subscription deleted {subscription_id} for {customer_email}")
    
    # TODO: Revoke product access
    # TODO: Send cancellation confirmation email
