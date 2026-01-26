"""Tests for Stripe webhook event handlers using actual webhook payloads."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.payments.stripe.router import (
    handle_invoice_payment_succeeded,
    handle_invoice_payment_failed,
)


# Load fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "stripe"


def load_fixture(filename: str) -> dict:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename) as f:
        return json.load(f)


@pytest.fixture
def invoice_paid_event():
    """Real invoice.paid webhook event from Stripe API 2025-12-15.clover."""
    return load_fixture("invoice_paid.json")


@pytest.fixture
def invoice_payment_succeeded_event():
    """Real invoice.payment_succeeded webhook event."""
    return load_fixture("invoice_payment_succeeded.json")


@pytest.fixture
def invoice_payment_paid_event():
    """Real invoice_payment.paid webhook event."""
    return load_fixture("invoice_payment_paid.json")


@pytest.mark.asyncio
@patch("src.payments.stripe.router.StripeClient")
@patch("src.payments.stripe.router.sync_subscription_to_db")
@patch("src.payments.stripe.router.send_subscription_confirmed_email_safe")
async def test_handle_invoice_paid_with_parent_structure(
    mock_email,
    mock_sync_sub,
    mock_stripe_client,
    invoice_paid_event,
):
    """Test invoice.paid handler extracts subscription ID from parent.subscription_details."""
    # Setup
    invoice_data = invoice_paid_event["data"]["object"]
    mock_subscription = MagicMock()
    mock_subscription.user_email = "testuser@example.com"
    mock_subscription.plan_name = "starter"
    mock_subscription.current_period_end = "1772137660"
    mock_sync_sub.return_value = mock_subscription

    # Mock Stripe client to return subscription
    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = {"id": "sub_1StwNu9vlzhgFql1HkCOfmOe", "status": "active"}
    mock_stripe_client.return_value = mock_client_instance

    # Execute
    await handle_invoice_payment_succeeded(invoice_data)

    # Verify subscription ID was extracted from parent.subscription_details
    mock_client_instance.get.assert_called_once_with("/subscriptions/sub_1StwNu9vlzhgFql1HkCOfmOe")

    # Verify sync was called with correct data
    assert mock_sync_sub.called
    call_args = mock_sync_sub.call_args[0]
    assert call_args[1] == "sub_1StwNu9vlzhgFql1HkCOfmOe"  # subscription_id
    assert call_args[2] == "cus_TrfjTkkqS2abOr"  # customer_id

    # Verify email was sent
    mock_email.assert_called_once()
    assert mock_email.call_args[1]["user_email"] == "testuser@example.com"


@pytest.mark.asyncio
@patch("src.payments.stripe.router.StripeClient")
@patch("src.payments.stripe.router.sync_subscription_to_db")
@patch("src.payments.stripe.router.send_subscription_confirmed_email_safe")
async def test_handle_invoice_payment_succeeded_with_parent_structure(
    mock_email,
    mock_sync_sub,
    mock_stripe_client,
    invoice_payment_succeeded_event,
):
    """Test invoice.payment_succeeded handler extracts subscription ID from parent."""
    # Setup
    invoice_data = invoice_payment_succeeded_event["data"]["object"]
    mock_subscription = MagicMock()
    mock_subscription.user_email = "testuser@example.com"
    mock_subscription.plan_name = "starter"
    mock_subscription.current_period_end = "1772137660"
    mock_sync_sub.return_value = mock_subscription

    # Mock Stripe client
    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = {"id": "sub_1StwNu9vlzhgFql1HkCOfmOe", "status": "active"}
    mock_stripe_client.return_value = mock_client_instance

    # Execute
    await handle_invoice_payment_succeeded(invoice_data)

    # Verify subscription ID extraction from parent.subscription_details
    mock_client_instance.get.assert_called_once_with("/subscriptions/sub_1StwNu9vlzhgFql1HkCOfmOe")

    # Verify metadata extraction
    assert invoice_data["parent"]["subscription_details"]["metadata"]["plan_key"] == "starter"
    assert invoice_data["parent"]["subscription_details"]["metadata"]["user_email"] == "testuser@example.com"


@pytest.mark.asyncio
@patch("src.payments.stripe.router.StripeClient")
@patch("src.payments.stripe.router.sync_subscription_to_db")
@patch("src.payments.stripe.router.send_subscription_confirmed_email_safe")
async def test_handle_invoice_payment_paid_fetches_invoice_first(
    mock_email,
    mock_sync_sub,
    mock_stripe_client,
    invoice_payment_paid_event,
):
    """Test invoice_payment.paid handler fetches invoice first then extracts subscription ID."""
    # Setup
    invoice_payment_data = invoice_payment_paid_event["data"]["object"]

    # Mock invoice response with parent structure (from invoice_paid fixture)
    mock_invoice = load_fixture("invoice_paid.json")["data"]["object"]

    mock_subscription = MagicMock()
    mock_subscription.user_email = "testuser@example.com"
    mock_subscription.plan_name = "starter"
    mock_subscription.current_period_end = "1772137660"
    mock_sync_sub.return_value = mock_subscription

    # Mock Stripe client - first call fetches invoice, second fetches subscription
    mock_client_instance = AsyncMock()
    mock_client_instance.get.side_effect = [
        mock_invoice,  # First call: fetch invoice
        {"id": "sub_1StwNu9vlzhgFql1HkCOfmOe", "status": "active"}  # Second call: fetch subscription
    ]
    mock_stripe_client.return_value = mock_client_instance

    # Execute
    await handle_invoice_payment_succeeded(invoice_payment_data)

    # Verify invoice was fetched first using the invoice ID from the invoice_payment object
    assert mock_client_instance.get.call_count == 2
    first_call = mock_client_instance.get.call_args_list[0][0][0]
    second_call = mock_client_instance.get.call_args_list[1][0][0]

    assert first_call == "/invoices/in_1StwNs9vlzhgFql13YkkvuP6"  # Fetch invoice
    assert second_call == "/subscriptions/sub_1StwNu9vlzhgFql1HkCOfmOe"  # Fetch subscription


@pytest.mark.asyncio
@patch("src.payments.stripe.router.StripeClient")
@patch("src.payments.stripe.router.sync_subscription_to_db")
@patch("src.payments.stripe.router.send_payment_failed_email_safe")
async def test_handle_invoice_payment_failed_with_parent_structure(
    mock_email,
    mock_sync_sub,
    mock_stripe_client,
    invoice_paid_event,
):
    """Test invoice.payment_failed handler extracts subscription ID from parent."""
    # Setup - reuse invoice_paid fixture but change status to failed
    invoice_data = invoice_paid_event["data"]["object"].copy()
    invoice_data["status"] = "open"  # Failed invoices are "open" not "paid"
    invoice_data["attempt_count"] = 1

    mock_subscription = MagicMock()
    mock_subscription.user_email = "testuser@example.com"
    mock_subscription.plan_name = "starter"
    mock_subscription.status = "past_due"
    mock_sync_sub.return_value = mock_subscription

    # Mock Stripe client
    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = {"id": "sub_1StwNu9vlzhgFql1HkCOfmOe", "status": "past_due"}
    mock_stripe_client.return_value = mock_client_instance

    # Execute
    await handle_invoice_payment_failed(invoice_data)

    # Verify subscription ID extraction
    mock_client_instance.get.assert_called_once_with("/subscriptions/sub_1StwNu9vlzhgFql1HkCOfmOe")

    # Verify failure email sent
    mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_invoice_payment_object_structure():
    """Test that invoice_payment objects have correct structure."""
    fixture = load_fixture("invoice_payment_paid.json")
    invoice_payment = fixture["data"]["object"]

    # Verify invoice_payment structure
    assert invoice_payment["object"] == "invoice_payment"
    assert invoice_payment["invoice"] == "in_1StwNs9vlzhgFql13YkkvuP6"
    assert invoice_payment["amount_paid"] == 2900
    assert invoice_payment["status"] == "paid"

    # Verify it does NOT have customer or subscription fields directly
    assert "customer" not in invoice_payment
    assert "subscription" not in invoice_payment
    # These fields are on the invoice object that needs to be fetched


@pytest.mark.asyncio
async def test_invoice_parent_structure():
    """Test that invoice objects have parent.subscription_details structure."""
    fixture = load_fixture("invoice_paid.json")
    invoice = fixture["data"]["object"]

    # Verify new Stripe API structure (2025-12-15.clover)
    assert "parent" in invoice
    assert invoice["parent"]["type"] == "subscription_details"
    assert "subscription_details" in invoice["parent"]

    subscription_details = invoice["parent"]["subscription_details"]
    assert subscription_details["subscription"] == "sub_1StwNu9vlzhgFql1HkCOfmOe"
    assert subscription_details["metadata"]["plan_key"] == "starter"
    assert subscription_details["metadata"]["user_email"] == "testuser@example.com"
    assert subscription_details["metadata"]["billing_cycle"] == "monthly"
