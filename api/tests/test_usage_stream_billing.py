"""The usage stream charges messages and crawled pages to the owner of the account they happened in."""

from datetime import datetime, timezone

import pytest
from boto3.dynamodb.types import TypeSerializer

from lambdas.usage_stream_handler import handler as usage_handler
from src.accounts import AccountService, Member
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.identity import IdentityRepository
from src.rate_limits.repository import UsageRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for

OWNER, MEMBER = user_id_for(TEST_USER_EMAIL), user_id_for(TEST_USER_EMAIL_2)
NOW = datetime.now(timezone.utc)
PERIOD = NOW.strftime("%Y-%m")


@pytest.fixture
def team(dynamodb_table) -> str:
    """An account owned by TEST_USER_EMAIL, with TEST_USER_EMAIL_2 as a member."""
    account_id = AccountService().create_account(IdentityRepository().get(OWNER), "Team").account_id
    member = IdentityRepository().get(MEMBER)
    dynamodb_table.put_item(Item=Member(
        account_id=account_id, user_id=MEMBER, email=member.email, name=member.name, invited_by=OWNER,
    ).to_dynamo_item())
    return account_id


def stream(entity: dict, event_id: str = "event-1", event_name: str = "INSERT") -> None:
    image = {key: TypeSerializer().serialize(value) for key, value in entity.items()}
    record = {"eventName": event_name, "eventID": event_id, "dynamodb": {"NewImage": image}}
    assert usage_handler.handler({"Records": [record]}, context=None) == {"status": "ok"}


def usage(email: str):
    return UsageRepository().get_usage(email, PERIOD)


def conversation_in(account_id: str) -> str:
    saved = ConversationRepository().save(Conversation(
        title="Chat", agent_id="agent-1", account_id=account_id, created_by=MEMBER,
    ))
    return saved.conversation_id


def message(conversation_id: str, sender_email: str = TEST_USER_EMAIL_2) -> dict:
    return {"entity_type": "Message", "conversation_id": conversation_id, "created_by": sender_email,
            "created_at": NOW.isoformat()}


def crawled_page(**fields) -> dict:
    return {"entity_type": "CrawledPage", "status": "success", "crawled_at": NOW.isoformat(),
            "created_by": MEMBER, **fields}


def test_a_members_message_is_charged_to_the_account_owner(team):
    stream(message(conversation_in(team)))

    assert usage(TEST_USER_EMAIL).messages_used == 1
    assert usage(TEST_USER_EMAIL_2) is None


def test_a_crawled_page_is_charged_to_the_account_owner(team):
    stream(crawled_page(account_id=team))

    assert usage(TEST_USER_EMAIL).kb_pages_used == 1
    assert usage(TEST_USER_EMAIL_2) is None


def test_a_crawled_page_that_finishes_later_is_charged_once_to_the_owner(team):
    pending = {"status": "pending", "account_id": team}
    stream(crawled_page(**pending))
    assert usage(TEST_USER_EMAIL) is None

    record = {"eventName": "MODIFY", "eventID": "event-2", "dynamodb": {
        "OldImage": {k: TypeSerializer().serialize(v) for k, v in crawled_page(**pending).items()},
        "NewImage": {k: TypeSerializer().serialize(v) for k, v in crawled_page(account_id=team).items()},
    }}
    usage_handler.handler({"Records": [record]}, context=None)

    assert usage(TEST_USER_EMAIL).kb_pages_used == 1


def test_a_page_that_never_recorded_its_account_is_not_charged_to_anyone(team):
    stream(crawled_page())

    assert usage(TEST_USER_EMAIL) is None and usage(TEST_USER_EMAIL_2) is None


def test_a_message_whose_conversation_cannot_be_found_is_charged_to_its_author(team):
    stream(message("no-such-conversation"))

    assert usage(TEST_USER_EMAIL_2).messages_used == 1
    assert usage(TEST_USER_EMAIL) is None


def test_agents_are_not_counted_here(team):
    stream({"entity_type": "Agent", "account_id": team, "owner_id": MEMBER})

    assert usage(TEST_USER_EMAIL) is None and usage(TEST_USER_EMAIL_2) is None


def test_the_same_event_is_counted_once(team):
    conversation_id = conversation_in(team)
    stream(message(conversation_id), event_id="same")
    stream(message(conversation_id), event_id="same")

    assert usage(TEST_USER_EMAIL).messages_used == 1
