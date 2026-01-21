from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Subscription:
    subscription_id: str
    user_email: str
    customer_id: Optional[str] = None
    status: Optional[str] = None
    plan_name: Optional[str] = None
    price_id: Optional[str] = None
    billing_cycle: Optional[str] = None
    current_period_end: Optional[str] = None
    latest_invoice_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        now = datetime.utcnow().isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return f"Subscription#{self.subscription_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "subscription_id": self.subscription_id,
            "user_email": self.user_email,
            "customer_id": self.customer_id,
            "status": self.status,
            "plan_name": self.plan_name,
            "price_id": self.price_id,
            "billing_cycle": self.billing_cycle,
            "current_period_end": self.current_period_end,
            "latest_invoice_id": self.latest_invoice_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "Subscription":
        return cls(
            subscription_id=item["subscription_id"],
            user_email=item["user_email"],
            customer_id=item.get("customer_id"),
            status=item.get("status"),
            plan_name=item.get("plan_name"),
            price_id=item.get("price_id"),
            billing_cycle=item.get("billing_cycle"),
            current_period_end=item.get("current_period_end"),
            latest_invoice_id=item.get("latest_invoice_id"),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
