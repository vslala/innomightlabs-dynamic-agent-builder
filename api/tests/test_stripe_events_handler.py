from unittest.mock import Mock

import stripe

from src.config import settings
from src.payments.subscriptions import SubscriptionRepository
from src.users import UserRepository
from lambdas.stripe_events_handler import handler as stripe_handler


def test_handler_persists_subscription_and_user(dynamodb_table, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")

    event = {
        "detail": {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_123",
                    "customer": "cus_123",
                    "status": "active",
                    "metadata": {"user_email": "user@example.com"},
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                    "cancel_at_period_end": False,
                    "canceled_at": None,
                    "trial_end": None,
                    "latest_invoice": "in_123",
                    "items": {
                        "data": [
                            {
                                "price": {
                                    "id": "price_123",
                                    "currency": "gbp",
                                    "unit_amount": 2900,
                                    "recurring": {"interval": "month"},
                                    "metadata": {"plan_key": "starter", "billing_cycle": "monthly"},
                                }
                            }
                        ]
                    },
                }
            },
        }
    }

    response = stripe_handler.handler(event, None)

    assert response["status"] == "ok"
    subscription = SubscriptionRepository().get_by_id("user@example.com", "sub_123")
    assert subscription is not None
    assert subscription.plan_name == "starter"
    assert subscription.billing_cycle == "monthly"
    assert subscription.currency == "gbp"
    assert subscription.amount == 2900

    user = UserRepository().get_by_email("user@example.com")
    assert user is not None
    assert user.stripe_customer_id == "cus_123"


def test_handler_skips_when_email_missing(dynamodb_table, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test")
    monkeypatch.setattr(stripe.Customer, "retrieve", Mock(side_effect=Exception("boom")))

    event = {
        "detail": {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_456",
                    "customer": "cus_456",
                    "status": "active",
                    "metadata": {},
                    "items": {
                        "data": [
                            {
                                "price": {
                                    "id": "price_456",
                                    "currency": "gbp",
                                    "unit_amount": 9900,
                                    "recurring": {"interval": "month"},
                                    "metadata": {"plan_key": "pro", "billing_cycle": "monthly"},
                                }
                            }
                        ]
                    },
                }
            },
        }
    }

    response = stripe_handler.handler(event, None)

    assert response["status"] == "ok"
    items = dynamodb_table.scan().get("Items", [])
    assert not any(item.get("sk", "").startswith("Subscription#") for item in items)
