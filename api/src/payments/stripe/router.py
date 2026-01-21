"""
Simplified Stripe payments integration.

Handles:
- Pricing plans display
- Checkout session creation
- Webhook events for subscription updates
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...config import settings
from ..pricing_config import get_pricing_config
from ...users import User, UserRepository
from ..subscriptions import Subscription, SubscriptionRepository

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/stripe", tags=["payments"])


# ============================================================================
# Response Models
# ============================================================================


class PricingTier(BaseModel):
    name: str
    badge: str
    description: str
    prices: dict[str, str]
    planKey: Optional[str] = None
    ctaLabel: str
    ctaHref: str
    highlighted: bool = False
    features: list[str]


class PricingFaq(BaseModel):
    question: str
    answer: str


class PricingResponse(BaseModel):
    tiers: list[PricingTier]
    faqs: list[PricingFaq]


class CheckoutRequest(BaseModel):
    planKey: str
    billingCycle: str  # 'monthly' or 'annual'
    userEmail: Optional[str] = None


class CheckoutResponse(BaseModel):
    url: str


# ============================================================================
# Pricing Endpoint (Public)
# ============================================================================


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing():
    """Get pricing tiers and FAQs."""
    config = get_pricing_config()

    tiers = [
        PricingTier(
            name=tier.name,
            badge=tier.badge,
            description=tier.description,
            prices=tier.prices,
            planKey=tier.key if tier.stripe_price_ids else None,
            ctaLabel=tier.cta.label,
            ctaHref=tier.cta.href,
            highlighted=tier.highlighted,
            features=tier.features,
        )
        for tier in config.tiers
    ]

    faqs = [
        PricingFaq(
            question="Do annual plans include a discount?",
            answer="Yes. Annual billing saves 17%, equivalent to two months free.",
        ),
        PricingFaq(
            question="Can I change plans later?",
            answer="Absolutely. Upgrade or downgrade anytime from your dashboard.",
        ),
        PricingFaq(
            question="What happens if I exceed my limits?",
            answer="You'll be prompted to upgrade. No overages - your usage is capped at your plan limits.",
        ),
    ]

    return PricingResponse(tiers=tiers, faqs=faqs)


# ============================================================================
# Checkout Session Creation
# ============================================================================


def _require_stripe_config() -> None:
    """Verify Stripe is configured."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")


def _require_webhook_config() -> None:
    """Verify webhook secret is configured."""
    _require_stripe_config()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")


async def _stripe_post(path: str, data: dict) -> dict:
    """Make a POST request to Stripe API."""
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, data=data, headers=headers)

    if response.status_code >= 400:
        log.error(f"Stripe API error {response.status_code}: {response.text}")
        raise HTTPException(status_code=502, detail="Stripe API request failed")

    return response.json()


async def _stripe_get(path: str) -> dict:
    """Make a GET request to Stripe API."""
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code >= 400:
        log.error(f"Stripe API error {response.status_code}: {response.text}")
        raise HTTPException(status_code=502, detail="Stripe API request failed")

    return response.json()


def _get_price_id(plan_key: str, billing_cycle: str) -> str:
    """Get Stripe price ID for a plan and billing cycle."""
    config = get_pricing_config()

    for tier in config.tiers:
        if tier.key == plan_key:
            return tier.stripe_price_ids.get(billing_cycle, "")

    return ""


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(payload: CheckoutRequest):
    """
    Create a Stripe checkout session.

    Simple flow:
    1. Get price ID from config
    2. Create checkout session
    3. Return checkout URL
    """
    _require_stripe_config()

    price_id = _get_price_id(payload.planKey, payload.billingCycle)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Plan '{payload.planKey}' with '{payload.billingCycle}' billing not found",
        )

    success_url = f"{settings.frontend_url}/payments/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.frontend_url}/payments/cancel"

    session_data = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "allow_promotion_codes": "true",
        "subscription_data[metadata][plan_key]": payload.planKey,
        "subscription_data[metadata][billing_cycle]": payload.billingCycle,
    }

    # Add customer email if provided
    if payload.userEmail:
        session_data["customer_email"] = payload.userEmail
        session_data["subscription_data[metadata][user_email]"] = payload.userEmail

    response = await _stripe_post("/checkout/sessions", session_data)

    return CheckoutResponse(url=response["url"])


# ============================================================================
# Session Exchange (Get JWT After Payment)
# ============================================================================


class SessionAuthResponse(BaseModel):
    token: str
    email: str
    subscription_status: Optional[str] = None


@router.get("/session/{session_id}", response_model=SessionAuthResponse)
async def exchange_session_for_auth(session_id: str):
    """
    Exchange Stripe session ID for JWT token.

    Flow:
    1. User completes payment, redirected to /payments/success?session_id=xyz
    2. Frontend calls this endpoint with session_id
    3. We fetch session from Stripe, get customer email
    4. Create user if doesn't exist
    5. Return JWT token
    6. Frontend saves JWT and polls for subscription to appear

    This allows anonymous users to checkout and automatically get authenticated.
    """
    _require_stripe_config()

    # Fetch session from Stripe
    try:
        session = await _stripe_get(f"/checkout/sessions/{session_id}")
    except HTTPException as e:
        log.error(f"Failed to fetch session {session_id}: {e}")
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Verify session is actually completed
    payment_status = session.get("payment_status")
    if payment_status != "paid":
        raise HTTPException(
            status_code=400,
            detail=f"Payment not completed. Status: {payment_status}",
        )

    # Get customer email
    customer_email = session.get("customer_details", {}).get("email")
    if not customer_email:
        customer_id = session.get("customer")
        if customer_id:
            customer = await _stripe_get(f"/customers/{customer_id}")
            customer_email = customer.get("email")

    if not customer_email:
        raise HTTPException(status_code=400, detail="No email found in session")

    # Create or get user
    from ...auth.jwt_utils import create_access_token

    _ensure_user_exists(customer_email, customer_id=session.get("customer"))

    user_repo = UserRepository()
    user = user_repo.get_by_email(customer_email)

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # Generate JWT token
    jwt_token = create_access_token(user)

    # Check if subscription exists yet (webhook might not have fired)
    subscription_repo = SubscriptionRepository()
    subscription = subscription_repo.get_active_for_user(customer_email)

    return SessionAuthResponse(
        token=jwt_token,
        email=customer_email,
        subscription_status=subscription.status if subscription else None,
    )


# ============================================================================
# Subscription Status
# ============================================================================


class SubscriptionStatusResponse(BaseModel):
    tier: str
    status: Optional[str] = None
    current_period_end: Optional[str] = None
    is_active: bool


@router.get("/subscription/status")
async def get_subscription_status(request: Request):
    """
    Get current subscription status for authenticated user.

    Used by frontend to:
    1. Poll after payment until subscription appears
    2. Display subscription info in dashboard
    """
    # Get user email from request state (set by auth middleware)
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    subscription_repo = SubscriptionRepository()
    subscription = subscription_repo.get_active_for_user(user_email)

    if subscription:
        return SubscriptionStatusResponse(
            tier=subscription.plan_name or "free",
            status=subscription.status,
            current_period_end=subscription.current_period_end,
            is_active=True,
        )
    else:
        return SubscriptionStatusResponse(
            tier="free",
            status=None,
            current_period_end=None,
            is_active=False,
        )


# ============================================================================
# Webhook Handler
# ============================================================================


def _extract_subscription_data(stripe_sub: dict) -> tuple[str, str, str]:
    """
    Extract plan info from Stripe subscription.

    Returns:
        (plan_key, billing_cycle, price_id)
    """
    metadata = stripe_sub.get("metadata", {})
    plan_key = metadata.get("plan_key", "free")
    billing_cycle = metadata.get("billing_cycle", "monthly")

    items = stripe_sub.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None

    return plan_key, billing_cycle, price_id


def _ensure_user_exists(email: str, customer_id: Optional[str] = None) -> None:
    """Create user if doesn't exist, update customer_id if provided."""
    repo = UserRepository()
    user = repo.get_by_email(email)

    if user:
        if customer_id:
            repo.update_stripe_customer_id(email, customer_id)
    else:
        name = email.split("@")[0]
        new_user = User(email=email, name=name, stripe_customer_id=customer_id)
        repo.create_or_update(new_user)


def _verify_webhook_signature(payload: bytes, signature_header: str) -> None:
    """
    Verify Stripe webhook signature.

    Args:
        payload: Raw request body
        signature_header: Value of 'stripe-signature' header

    Raises:
        HTTPException: If signature is invalid or timestamp is too old
    """
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    # Parse signature header
    timestamp = None
    signatures = []
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if not timestamp or not signatures:
        raise HTTPException(status_code=400, detail="Invalid signature header format")

    # Compute expected signature
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected_sig = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # Compare signatures (constant-time comparison)
    if not any(hmac.compare_digest(expected_sig, sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Check timestamp tolerance (5 minutes)
    tolerance = 300  # seconds
    try:
        timestamp_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp in signature")

    if abs(time.time() - timestamp_int) > tolerance:
        raise HTTPException(status_code=400, detail="Signature timestamp too old")


@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handle Stripe webhooks.

    Processes:
    - checkout.session.completed: New subscription created
    - customer.subscription.updated: Subscription changed
    - customer.subscription.deleted: Subscription cancelled
    """
    _require_webhook_config()

    # Get raw payload and signature
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    # Verify signature
    _verify_webhook_signature(payload, signature)

    # Parse event
    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    log.info(f"Received Stripe webhook: {event_type}")

    repo = SubscriptionRepository()

    # Handle checkout completion
    if event_type == "checkout.session.completed":
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")
        customer_email = data.get("customer_details", {}).get("email")

        if not all([subscription_id, customer_id, customer_email]):
            log.warning("Incomplete checkout session data")
            return {"status": "ignored"}

        # Fetch full subscription details
        stripe_sub = await _stripe_get(f"/subscriptions/{subscription_id}")

        plan_key, billing_cycle, price_id = _extract_subscription_data(stripe_sub)

        subscription = Subscription(
            subscription_id=subscription_id,
            user_email=customer_email,
            customer_id=customer_id,
            status=stripe_sub.get("status"),
            plan_name=plan_key,
            price_id=price_id,
            billing_cycle=billing_cycle,
            current_period_end=str(stripe_sub.get("current_period_end")),
            latest_invoice_id=stripe_sub.get("latest_invoice"),
        )

        _ensure_user_exists(customer_email, customer_id)
        repo.upsert(subscription)

        log.info(f"Created subscription {subscription_id} for {customer_email}")

    # Handle subscription updates
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_id = data.get("id")
        customer_id = data.get("customer")

        if not customer_id:
            log.warning("No customer ID in subscription event")
            return {"status": "ignored"}

        # Get customer email
        customer = await _stripe_get(f"/customers/{customer_id}")

        customer_email = customer.get("email")
        if not customer_email:
            log.warning(f"No email for customer {customer_id}")
            return {"status": "ignored"}

        plan_key, billing_cycle, price_id = _extract_subscription_data(data)

        subscription = Subscription(
            subscription_id=subscription_id,
            user_email=customer_email,
            customer_id=customer_id,
            status=data.get("status"),
            plan_name=plan_key,
            price_id=price_id,
            billing_cycle=billing_cycle,
            current_period_end=str(data.get("current_period_end")),
            latest_invoice_id=data.get("latest_invoice"),
        )

        _ensure_user_exists(customer_email, customer_id)
        repo.upsert(subscription)

        log.info(f"Updated subscription {subscription_id} for {customer_email}")

    return {"status": "ok"}
