from fastapi import status
from tests.mock_data import TEST_USER_EMAIL
import time


def test_checkout_requires_authentication(test_client):
    """Unauthenticated users cannot access checkout."""
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "starter", "billingCycle": "monthly"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    detail = response.json()["detail"]
    assert "authorization" in detail.lower() or "authentication" in detail.lower()


def test_checkout_rejects_duplicate_plan(test_client, auth_headers, dynamodb_table):
    """User with active 'starter' plan cannot purchase 'starter' again."""
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    # Setup: Create active starter subscription
    repo = SubscriptionRepository()
    repo.upsert(Subscription(
        subscription_id="sub_123",
        user_email=TEST_USER_EMAIL,
        status="active",
        plan_name="starter",
        current_period_end=str(int(time.time()) + 86400 * 30)  # 30 days future
    ))

    # Test: Attempt to purchase starter again
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "starter", "billingCycle": "monthly"},
        headers=auth_headers
    )

    # Assert: Blocked with helpful message
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    detail = response.json()["detail"]
    assert "already have an active starter subscription" in detail
    assert "Settings" in detail


def test_checkout_rejects_downgrade(test_client, auth_headers, dynamodb_table):
    """User with 'pro' plan cannot purchase 'starter' plan via checkout."""
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    # Setup: Create active pro subscription
    repo = SubscriptionRepository()
    repo.upsert(Subscription(
        subscription_id="sub_pro",
        user_email=TEST_USER_EMAIL,
        status="active",
        plan_name="pro",
        current_period_end=str(int(time.time()) + 86400 * 30)
    ))

    # Test: Attempt to purchase starter (downgrade)
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "starter", "billingCycle": "monthly"},
        headers=auth_headers
    )

    # Assert: Blocked with downgrade message
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    detail = response.json()["detail"]
    assert "downgrade from pro to starter" in detail.lower()
    assert "Settings" in detail


def test_checkout_allows_upgrade(test_client, auth_headers, dynamodb_table, monkeypatch):
    """User with 'starter' plan can purchase 'pro' plan (upgrade)."""
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    # Setup: Create active starter subscription
    repo = SubscriptionRepository()
    repo.upsert(Subscription(
        subscription_id="sub_starter",
        user_email=TEST_USER_EMAIL,
        status="active",
        plan_name="starter",
        current_period_end=str(int(time.time()) + 86400 * 30)
    ))

    # Mock Stripe API call
    async def mock_stripe_post(self, path, data):
        return {"url": "https://checkout.stripe.com/session_xyz"}

    from src.payments.stripe.router import StripeClient
    monkeypatch.setattr(StripeClient, "post", mock_stripe_post)

    # Test: Purchase pro plan (upgrade)
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "pro", "billingCycle": "monthly"},
        headers=auth_headers
    )

    # Assert: Allowed
    assert response.status_code == status.HTTP_200_OK
    assert "url" in response.json()


def test_checkout_allows_no_active_subscription(test_client, auth_headers, dynamodb_table, monkeypatch):
    """User with no active subscription can purchase any plan."""
    # Mock Stripe API
    async def mock_stripe_post(self, path, data):
        return {"url": "https://checkout.stripe.com/session_xyz"}

    from src.payments.stripe.router import StripeClient
    monkeypatch.setattr(StripeClient, "post", mock_stripe_post)

    # Test: Purchase starter with no existing subscription
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "starter", "billingCycle": "monthly"},
        headers=auth_headers
    )

    # Assert: Allowed
    assert response.status_code == status.HTTP_200_OK


def test_checkout_allows_expired_resubscribe(test_client, auth_headers, dynamodb_table, monkeypatch):
    """User with expired subscription can resubscribe to same plan."""
    from src.payments.subscriptions import Subscription, SubscriptionRepository

    # Setup: Create expired subscription
    repo = SubscriptionRepository()
    repo.upsert(Subscription(
        subscription_id="sub_expired",
        user_email=TEST_USER_EMAIL,
        status="active",
        plan_name="starter",
        current_period_end=str(int(time.time()) - 86400)  # 1 day ago (expired)
    ))

    # Mock Stripe API
    async def mock_stripe_post(self, path, data):
        return {"url": "https://checkout.stripe.com/session_xyz"}

    from src.payments.stripe.router import StripeClient
    monkeypatch.setattr(StripeClient, "post", mock_stripe_post)

    # Test: Resubscribe to same plan
    response = test_client.post(
        "/payments/stripe/checkout",
        json={"planKey": "starter", "billingCycle": "monthly"},
        headers=auth_headers
    )

    # Assert: Allowed (expired subscriptions don't block checkout)
    assert response.status_code == status.HTTP_200_OK
