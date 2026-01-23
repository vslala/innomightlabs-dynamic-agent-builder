from typing import Optional

from pydantic import BaseModel, Field


class StripePrice(BaseModel):
    id: Optional[str] = None
    currency: Optional[str] = None
    unit_amount: Optional[int] = None
    recurring: Optional[dict] = None
    metadata: dict = Field(default_factory=dict)


class StripeSubscriptionItem(BaseModel):
    price: Optional[StripePrice] = None


class StripeSubscriptionData(BaseModel):
    id: Optional[str] = None
    customer: Optional[str] = None
    status: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    current_period_start: Optional[int] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: Optional[bool] = None
    canceled_at: Optional[int] = None
    trial_end: Optional[int] = None
    latest_invoice: Optional[str] = None
    items: dict = Field(default_factory=dict)

    def first_price(self) -> Optional[StripePrice]:
        items = (self.items or {}).get("data", [])
        if not items:
            return None
        return StripeSubscriptionItem.model_validate(items[0]).price


class StripePriceInfo(BaseModel):
    plan_key: Optional[str] = None
    billing_cycle: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[int] = None


class StripeCheckoutSession(BaseModel):
    subscription: Optional[str] = None


class StripeInvoice(BaseModel):
    id: Optional[str] = None
    subscription: Optional[str] = None
    customer: Optional[str] = None


class StripeEventData(BaseModel):
    object: dict = Field(default_factory=dict)


class StripeEvent(BaseModel):
    type: Optional[str] = None
    data: StripeEventData = Field(default_factory=StripeEventData)
