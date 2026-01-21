import json
import hmac
import hashlib
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
import logging
from pydantic import BaseModel

from ...config import settings
from ...users import User, UserRepository
from ..subscriptions import Subscription, SubscriptionRepository

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/stripe", tags=["payments", "stripe"])


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


class PricingAddOn(BaseModel):
    title: str
    price: str
    description: str


class PricingFaq(BaseModel):
    question: str
    answer: str


class PricingResponse(BaseModel):
    tiers: list[PricingTier]
    addOns: list[PricingAddOn]
    faqs: list[PricingFaq]


PRICING_RESPONSE = PricingResponse(
    tiers=[
        PricingTier(
            name="Free",
            badge="Free forever",
            description="Get started with core memory features for personal projects.",
            prices={"monthly": "$0", "annual": "$0"},
            planKey=None,
            ctaLabel="Join the Waitlist",
            ctaHref="/#waitlist",
            features=[
                "1 agent",
                "100 messages / month",
                "10 KB pages",
                "5 memory blocks",
                "Community support",
            ],
        ),
        PricingTier(
            name="Starter",
            badge="For growing teams",
            description="Scale your first production agents with more capacity.",
            prices={"monthly": "$29", "annual": "$290"},
            planKey="starter",
            ctaLabel="Start with Starter",
            ctaHref="/#waitlist",
            features=[
                "3 agents",
                "2,000 messages / month",
                "100 KB pages",
                "20 memory blocks",
                "Email support",
            ],
        ),
        PricingTier(
            name="Pro",
            badge="Most popular",
            description="Everything you need for serious agent workflows.",
            prices={"monthly": "$99", "annual": "$990"},
            planKey="pro",
            ctaLabel="Go Pro",
            ctaHref="/#waitlist",
            highlighted=True,
            features=[
                "10 agents",
                "10,000 messages / month",
                "1,000 KB pages",
                "Unlimited memory blocks",
                "Priority support",
            ],
        ),
        PricingTier(
            name="Enterprise",
            badge="Custom",
            description="Dedicated support and limitless scale for large teams.",
            prices={"monthly": "Custom", "annual": "Custom"},
            planKey=None,
            ctaLabel="Contact Sales",
            ctaHref="/#waitlist",
            features=[
                "Unlimited agents",
                "Unlimited messages",
                "Unlimited KB pages",
                "Unlimited memory blocks",
                "Dedicated support",
            ],
        ),
    ],
    addOns=[
        PricingAddOn(
            title="Extra Messages",
            price="$5 per 1,000",
            description="Top up monthly message limits as usage grows.",
        ),
        PricingAddOn(
            title="Extra Agent",
            price="$15 per agent",
            description="Add more agents beyond your plan limit.",
        ),
        PricingAddOn(
            title="Extra KB Pages",
            price="$3 per 100 pages",
            description="Expand knowledge base capacity on demand.",
        ),
        PricingAddOn(
            title="API Access",
            price="$8 per 1,000 calls",
            description="Metered API usage for Pro and above.",
        ),
    ],
    faqs=[
        PricingFaq(
            question="Do annual plans include a discount?",
            answer="Yes. Annual billing saves 17%, which is equivalent to two months free.",
        ),
        PricingFaq(
            question="What happens if I exceed my plan limits?",
            answer="You can add usage-based add-ons for messages, agents, and KB pages.",
        ),
        PricingFaq(
            question="Can I change plans later?",
            answer="Absolutely. You can upgrade or downgrade at any time from the billing page.",
        ),
    ],
)


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing():
    return PRICING_RESPONSE


class CheckoutSessionRequest(BaseModel):
    planKey: str
    billingCycle: str
    customerEmail: Optional[str] = None
    clientReferenceId: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    id: str
    url: str


def _require_stripe_config() -> None:
    missing = []
    if not settings.stripe_secret_key:
        missing.append("STRIPE_SECRET_KEY")
    if not settings.stripe_webhook_secret:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing Stripe configuration: {', '.join(missing)}")


def _price_id_for(plan_key: str, billing_cycle: str) -> str:
    billing_cycle = billing_cycle.lower()
    if plan_key == "starter":
        return (
            settings.stripe_price_starter_monthly
            if billing_cycle == "monthly"
            else settings.stripe_price_starter_annual
        )
    if plan_key == "pro":
        return (
            settings.stripe_price_pro_monthly
            if billing_cycle == "monthly"
            else settings.stripe_price_pro_annual
        )
    return ""


def _price_env_for(plan_key: str, billing_cycle: str) -> str:
    if plan_key == "starter" and billing_cycle == "monthly":
        return "STRIPE_PRICE_STARTER_MONTHLY"
    if plan_key == "starter" and billing_cycle == "annual":
        return "STRIPE_PRICE_STARTER_ANNUAL"
    if plan_key == "pro" and billing_cycle == "monthly":
        return "STRIPE_PRICE_PRO_MONTHLY"
    if plan_key == "pro" and billing_cycle == "annual":
        return "STRIPE_PRICE_PRO_ANNUAL"
    return "STRIPE_PRICE_UNKNOWN"


def _plan_from_price_id(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    mapping = {
        settings.stripe_price_starter_monthly: "starter",
        settings.stripe_price_starter_annual: "starter",
        settings.stripe_price_pro_monthly: "pro",
        settings.stripe_price_pro_annual: "pro",
    }
    return mapping.get(price_id)


async def _stripe_request(method: str, path: str, data: Optional[dict] = None) -> dict:
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {settings.stripe_secret_key}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, url, data=data, headers=headers)
    if response.status_code >= 400:
        log.error("Stripe API error %s: %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail="Stripe API request failed")
    return response.json()


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(payload: CheckoutSessionRequest, request: Request):
    _require_stripe_config()

    plan_key = payload.planKey.lower()
    billing_cycle = payload.billingCycle.lower()
    price_id = _price_id_for(plan_key, billing_cycle)
    if not price_id:
        env_key = _price_env_for(plan_key, billing_cycle)
        raise HTTPException(status_code=500, detail=f"Missing Stripe price configuration: {env_key}")

    success_url = f"{settings.frontend_url}/payments/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.frontend_url}/payments/cancel"

    data = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "allow_promotion_codes": "true",
        "metadata[plan_key]": plan_key,
        "metadata[billing_cycle]": billing_cycle,
        "subscription_data[metadata][plan_key]": plan_key,
        "subscription_data[metadata][billing_cycle]": billing_cycle,
    }
    if payload.customerEmail:
        data["customer_email"] = payload.customerEmail
        data["metadata[user_email]"] = payload.customerEmail
        data["subscription_data[metadata][user_email]"] = payload.customerEmail
    if payload.clientReferenceId:
        data["client_reference_id"] = payload.clientReferenceId

    response = await _stripe_request("POST", "/checkout/sessions", data=data)
    return CheckoutSessionResponse(id=response["id"], url=response["url"])


def _verify_signature(payload: str, signature_header: str) -> None:
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    timestamp = None
    signatures = []
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if not timestamp or not signatures:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature header")

    signed_payload = f"{timestamp}.{payload}".encode("utf-8")
    expected = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    tolerance = 300
    if abs(time.time() - int(timestamp)) > tolerance:
        raise HTTPException(status_code=400, detail="Stripe signature timestamp out of tolerance")


def _subscription_from_stripe(
    stripe_subscription: dict,
    user_email: str,
    plan_name: Optional[str],
    billing_cycle: Optional[str],
) -> Subscription:
    price_id = None
    items = stripe_subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")

    current_period_end = stripe_subscription.get("current_period_end")
    current_period_end_iso = None
    if current_period_end:
        current_period_end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_period_end))

    return Subscription(
        subscription_id=stripe_subscription["id"],
        user_email=user_email,
        customer_id=stripe_subscription.get("customer"),
        status=stripe_subscription.get("status"),
        plan_name=plan_name,
        price_id=price_id,
        billing_cycle=billing_cycle,
        current_period_end=current_period_end_iso,
        latest_invoice_id=stripe_subscription.get("latest_invoice"),
    )


def _ensure_user(email: str, name_hint: Optional[str] = None, customer_id: Optional[str] = None) -> None:
    repo = UserRepository()
    existing = repo.get_by_email(email)
    if existing:
        if customer_id:
            repo.update_stripe_customer_id(email, customer_id)
        return
    name = name_hint or email.split("@")[0]
    user = User(email=email, name=name, stripe_customer_id=customer_id)
    repo.create_or_update(user)

@router.post("/webhook")
async def handle_payment_events(request: Request):
    _require_stripe_config()
    payload_bytes = await request.body()
    payload = payload_bytes.decode("utf-8")
    signature = request.headers.get("stripe-signature", "")

    try:
        _verify_signature(payload, signature)
        event = json.loads(payload)
    except json.JSONDecodeError:
        log.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event.get("type")
    event_data = event.get("data", {}).get("object", {})
    log.info("Received Stripe event: %s", event_type)

    repo = SubscriptionRepository()

    if event_type == "checkout.session.completed":
        subscription_id = event_data.get("subscription")
        customer_id = event_data.get("customer")
        metadata = event_data.get("metadata") or {}
        customer_email = metadata.get("user_email") or (event_data.get("customer_details") or {}).get("email")
        if subscription_id and customer_id and customer_email:
            stripe_subscription = await _stripe_request("GET", f"/subscriptions/{subscription_id}")
            subscription_metadata = stripe_subscription.get("metadata") or {}
            plan_key = subscription_metadata.get("plan_key") or metadata.get("plan_key")
            billing_cycle = subscription_metadata.get("billing_cycle") or metadata.get("billing_cycle")
            subscription = _subscription_from_stripe(
                stripe_subscription,
                customer_email,
                plan_key,
                billing_cycle,
            )
            _ensure_user(customer_email, customer_id=customer_id)
            repo.upsert(subscription)

    if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        customer_id = event_data.get("customer")
        if customer_id:
            customer = await _stripe_request("GET", f"/customers/{customer_id}")
            customer_email = customer.get("email")
            if customer_email:
                metadata = event_data.get("metadata") or {}
                price_id = None
                items = event_data.get("items", {}).get("data", [])
                if items:
                    price_id = items[0].get("price", {}).get("id")
                plan_key = metadata.get("plan_key") or _plan_from_price_id(price_id)
                billing_cycle = metadata.get("billing_cycle")
                subscription = _subscription_from_stripe(
                    event_data,
                    customer_email,
                    plan_key,
                    billing_cycle,
                )
                _ensure_user(customer_email, customer_id=customer_id)
                repo.upsert(subscription)

    return {"status": "ok"}
