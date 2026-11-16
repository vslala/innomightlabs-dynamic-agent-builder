"""Seat limits come from the owner's plan: written when an account is created, kept in step when the plan changes
(the Stripe webhook), and backfilled for accounts from before. Invitations read them."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.accounts import AccountRepository, AccountService, Member
from src.config import settings
from src.iam.invitations.service import InvitationService
from src.iam.service import IamError
from src.identity import IdentityRepository
from src.payments.stripe.router import sync_subscription_to_db
from src.payments.subscriptions import Subscription, SubscriptionRepository
from src.rate_limits.service import RateLimitService
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for

OWNER, OTHER = user_id_for(TEST_USER_EMAIL), user_id_for(TEST_USER_EMAIL_2)
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backfill_account_seat_limits.py"


@pytest.fixture(autouse=True)
def no_superusers(monkeypatch):
    monkeypatch.setattr(settings, "superuser_emails", [])


def subscribe(email: str, plan: str, status: str = "active") -> None:
    SubscriptionRepository().upsert(Subscription(subscription_id=f"sub_{plan}", user_email=email, status=status,
                                                 plan_name=plan, customer_id="cus_1"))


def create(user_id: str, name: str) -> str:
    identity = IdentityRepository().get(user_id)
    assert identity is not None
    return AccountService().create_account(identity, name).account_id


def seat_limit(account_id: str) -> int | None:
    account = AccountRepository().get(account_id)
    assert account is not None
    return account.seat_limit


def load_script():
    spec = importlib.util.spec_from_file_location("backfill_account_seat_limits", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_new_account_gets_the_free_plans_seats(dynamodb_table):
    assert seat_limit(create(OWNER, "Team")) == 1


def test_a_new_account_gets_the_owners_paid_plans_seats(dynamodb_table):
    subscribe(TEST_USER_EMAIL, "business")
    assert seat_limit(create(OWNER, "Team")) == 5


def test_a_superusers_and_an_unlimited_plans_accounts_are_unlimited(dynamodb_table, monkeypatch):
    subscribe(TEST_USER_EMAIL, "enterprise")
    assert seat_limit(create(OWNER, "Enterprise")) == 0
    monkeypatch.setattr(settings, "superuser_emails", [TEST_USER_EMAIL_2])
    assert seat_limit(create(OTHER, "Staff")) == 0


def test_a_plan_change_updates_every_account_the_owner_owns_and_no_other(dynamodb_table):
    first, second = create(OWNER, "One"), create(OWNER, "Two")
    theirs = create(OTHER, "Theirs")
    # The owner belonging to someone else's account doesn't make its seats theirs to set
    identity = IdentityRepository().get(OWNER)
    dynamodb_table.put_item(Item=Member(account_id=theirs, user_id=OWNER, email=identity.email,
                                        name=identity.name).to_dynamo_item())

    subscribe(TEST_USER_EMAIL, "growth")
    assert RateLimitService().sync_seat_limits(TEST_USER_EMAIL) >= 2

    assert (seat_limit(first), seat_limit(second), seat_limit(theirs)) == (20, 20, 1)


def test_a_cancelled_plan_falls_back_to_the_free_seats(dynamodb_table):
    subscribe(TEST_USER_EMAIL, "business")
    account = create(OWNER, "Team")
    subscribe(TEST_USER_EMAIL, "business", status="canceled")
    RateLimitService().sync_seat_limits(TEST_USER_EMAIL)
    assert seat_limit(account) == 1


@pytest.mark.asyncio
async def test_the_stripe_webhook_sync_updates_the_owners_seats(dynamodb_table):
    account = create(OWNER, "Team")
    stripe_subscription = {"status": "active", "metadata": {"plan_key": "business", "billing_cycle": "monthly"}}
    with patch("src.payments.stripe.router.get_customer_email", AsyncMock(return_value=TEST_USER_EMAIL)):
        await sync_subscription_to_db(stripe_subscription, "sub_live", "cus_live")
    assert seat_limit(account) == 5


def test_an_unlimited_account_invites_past_any_count(dynamodb_table, monkeypatch):
    monkeypatch.setattr(settings, "account_invite_pending_limit", 50, raising=False)
    subscribe(TEST_USER_EMAIL, "enterprise")
    account = create(OWNER, "Enterprise")
    service = InvitationService()
    for n in range(3):
        service.create(account, OWNER, f"person{n}@example.com")
    assert len(service.repository.invites(account)) == 3


def test_a_free_account_has_no_seat_for_an_invitation(dynamodb_table):
    account = create(OWNER, "Solo")
    with pytest.raises(IamError) as raised:
        InvitationService().create(account, OWNER, "person@example.com")
    assert raised.value.detail["code"] == "SEAT_LIMIT_REACHED"


def test_the_backfill_sets_missing_limits_only_and_a_dry_run_writes_nothing(dynamodb_table, capsys):
    script = load_script()
    subscribe(TEST_USER_EMAIL, "business")
    legacy, kept = create(OWNER, "Legacy"), create(OWNER, "Kept")
    dynamodb_table.update_item(Key={"pk": f"Account#{legacy}", "sk": "Account#Metadata"},
                               UpdateExpression="REMOVE seat_limit")
    AccountRepository().set_seat_limit(kept, 3)

    with patch.object(sys, "argv", ["backfill"]):
        script.main()
    assert seat_limit(legacy) is None
    assert f"would write: account {legacy} (Legacy) -> 5 seat(s)" in capsys.readouterr().out

    with patch.object(sys, "argv", ["backfill", "--apply"]):
        script.main()
    assert (seat_limit(legacy), seat_limit(kept)) == (5, 3)
    with patch.object(sys, "argv", ["backfill", "--apply"]):
        script.main()
    assert "0 account(s) given a seat limit" in capsys.readouterr().out.splitlines()[-1]
