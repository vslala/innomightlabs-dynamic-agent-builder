"""Tests for Stripe invoice webhook handlers with new API structure."""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock

from src.payments.stripe.router import handle_invoice_payment_succeeded
from src.payments.subscriptions import SubscriptionRepository


def test_handle_invoice_with_nested_subscription_new_api(dynamodb_table, monkeypatch):
    """Test handling invoice with subscription nested in parent.subscription_details (new Stripe API 2025-12-15+)."""

    # Mock subscription response
    subscription_data = {
        "id": "sub_test123",
        "customer": "cus_test123",
        "status": "active",
        "metadata": {
            "plan_key": "starter",
            "billing_cycle": "monthly",
            "user_email": "testuser@example.com"
        },
        "items": {
            "data": [{
                "price": {
                    "id": "price_123",
                    "currency": "gbp",
                    "unit_amount": 2900,
                    "recurring": {"interval": "month"},
                    "metadata": {
                        "plan_key": "starter",
                        "billing_cycle": "monthly"
                    }
                },
                "current_period_start": 1769305868,
                "current_period_end": 1771984268
            }]
        }
    }

    # Patch StripeClient
    from src.payments.stripe import router as stripe_router

    class MockStripeClient:
        async def get(self, path):
            # Return customer data for customer API calls
            if path.startswith("/customers/"):
                return {"id": "cus_test123", "email": "testuser@example.com"}
            # Return subscription data for subscription API calls
            return subscription_data

    monkeypatch.setattr(stripe_router, "StripeClient", lambda: MockStripeClient())

    # Invoice with NEW API structure (subscription in parent.subscription_details)
    invoice_data = {
        "id": "in_test123",
        "object": "invoice",
        "customer": "cus_test123",
        # NO top-level subscription field
        "parent": {
            "type": "subscription_details",
            "subscription_details": {
                "subscription": "sub_test123",  # Subscription nested here
                "metadata": {
                    "plan_key": "starter",
                    "user_email": "testuser@example.com",
                    "billing_cycle": "monthly"
                }
            }
        },
        "lines": {
            "data": [{
                "period": {
                    "start": 1769305868,
                    "end": 1771984268
                }
            }]
        },
        "status": "paid"
    }

    # Call handler
    asyncio.run(handle_invoice_payment_succeeded(invoice_data))

    # Verify subscription was created
    repo = SubscriptionRepository()
    subscription = repo.get_by_id("testuser@example.com", "sub_test123")

    assert subscription is not None
    assert subscription.subscription_id == "sub_test123"
    assert subscription.user_email == "testuser@example.com"
    assert subscription.plan_name == "starter"
    assert subscription.status == "active"
    assert subscription.current_period_start == "1769305868"
    assert subscription.current_period_end == "1771984268"


def test_handle_invoice_with_direct_subscription_old_api(dynamodb_table, monkeypatch):
    """Test handling invoice with direct subscription field (old Stripe API)."""

    # Mock subscription response
    subscription_data = {
        "id": "sub_old123",
        "customer": "cus_old123",
        "status": "active",
        "metadata": {
            "plan_key": "pro",
            "billing_cycle": "monthly",
            "user_email": "olduser@example.com"
        },
        "items": {
            "data": [{
                "price": {
                    "id": "price_456",
                    "currency": "gbp",
                    "unit_amount": 9900,
                    "recurring": {"interval": "month"},
                    "metadata": {
                        "plan_key": "pro",
                        "billing_cycle": "monthly"
                    }
                },
                "current_period_start": 1769305868,
                "current_period_end": 1771984268
            }]
        }
    }

    # Patch StripeClient
    from src.payments.stripe import router as stripe_router

    class MockStripeClient:
        async def get(self, path):
            # Return customer data for customer API calls
            if path.startswith("/customers/"):
                return {"id": "cus_old123", "email": "olduser@example.com"}
            # Return subscription data for subscription API calls
            return subscription_data

    monkeypatch.setattr(stripe_router, "StripeClient", lambda: MockStripeClient())

    # Invoice with OLD API structure (direct subscription field)
    invoice_data = {
        "id": "in_old123",
        "object": "invoice",
        "subscription": "sub_old123",  # Direct subscription field
        "customer": "cus_old123",
        "lines": {
            "data": [{
                "period": {
                    "start": 1769305868,
                    "end": 1771984268
                }
            }]
        },
        "status": "paid"
    }

    # Call handler
    asyncio.run(handle_invoice_payment_succeeded(invoice_data))

    # Verify subscription was created
    repo = SubscriptionRepository()
    subscription = repo.get_by_id("olduser@example.com", "sub_old123")

    assert subscription is not None
    assert subscription.subscription_id == "sub_old123"
    assert subscription.user_email == "olduser@example.com"
    assert subscription.plan_name == "pro"
    assert subscription.status == "active"


def test_handle_invoice_missing_subscription_logs_warning(dynamodb_table, monkeypatch, caplog):
    """Test that missing subscription logs warning and returns early."""

    # Invoice with NO subscription anywhere
    invoice_data = {
        "id": "in_nosub",
        "object": "invoice",
        "customer": "cus_nosub",
        "status": "paid"
    }

    # Call handler
    asyncio.run(handle_invoice_payment_succeeded(invoice_data))

    # Verify warning was logged
    assert "Invoice data missing subscription or customer" in caplog.text

    # Verify no subscription was created
    repo = SubscriptionRepository()
    items = repo.table.scan().get("Items", [])
    subscription_items = [item for item in items if "Subscription#" in item.get("sk", "")]
    assert len(subscription_items) == 0
