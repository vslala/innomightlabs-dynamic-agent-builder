from typing import Optional

from pydantic import BaseModel


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
    billingCycle: str
    userEmail: Optional[str] = None

class CheckoutResponse(BaseModel):
    url: str

class SessionAuthResponse(BaseModel):
    token: str
    email: str
    subscription_status: Optional[str] = None

class SubscriptionStatusResponse(BaseModel):
    tier: str
    status: Optional[str] = None
    current_period_end: Optional[str] = None
    is_active: bool