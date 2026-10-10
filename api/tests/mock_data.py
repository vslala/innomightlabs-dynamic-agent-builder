"""
Reusable mock data for tests.
"""

from uuid import NAMESPACE_URL, uuid5

# Test user data
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_EMAIL_2 = "otheruser@example.com"


#: conftest seeds an identity, and its personal account, for each of these
SEEDED_EMAILS = (TEST_USER_EMAIL, TEST_USER_EMAIL_2, "someone-else@example.com", "owner@example.com")


def user_id_for(email: str) -> str:
    """The user_id conftest gives the identity it seeds for this email, so tests can sign tokens for it."""
    return str(uuid5(NAMESPACE_URL, f"identity:{email}"))


def owner_for(email: str):
    """The seeded person with this email, in their personal account: whose agents tests create."""
    from src.accounts import Owner, personal_account_id

    user_id = user_id_for(email)
    return Owner(account_id=personal_account_id(user_id), user_id=user_id, email=email)


def account_for(email: str = TEST_USER_EMAIL) -> str:
    """The person's personal account: where tests keep the settings and credentials it holds."""
    return owner_for(email).account_id


def owner_ids(email: str = TEST_USER_EMAIL) -> tuple[str, str]:
    """(account_id, user_id) of the seeded person, for repository calls that take an owner."""
    owner = owner_for(email)
    return owner.account_id, owner.user_id


def agent_fields(email: str = TEST_USER_EMAIL) -> dict:
    """The ownership fields an `Agent(...)` built in a test needs: owned by `email`, in their personal account."""
    owner = owner_for(email)
    return {"account_id": owner.account_id, "owner_id": owner.user_id, "created_by": owner.user_id}


def kb_fields(email: str = TEST_USER_EMAIL) -> dict:
    """The ownership fields a `KnowledgeBase(...)` built in a test needs: like an agent's."""
    return agent_fields(email)


def conversation_fields(email: str = TEST_USER_EMAIL) -> dict:
    """What a `Conversation(...)` built in a test needs: started by `email`, in their personal account."""
    owner = owner_for(email)
    return {"account_id": owner.account_id, "created_by": owner.user_id}


def conversations_of(email: str = TEST_USER_EMAIL) -> str:
    """The partition a seeded person's conversations live in, in their personal account."""
    return owner_for(email).member_pk

# Agent creation request data
AGENT_CREATE_REQUEST = {
    "agent_name": "Test Agent",
    "agent_architecture": "krishna-mini",
    "agent_provider": "Bedrock",
    "agent_provider_api_key": "test-api-key-123",
    "agent_persona": "You are a helpful test assistant.",
}

AGENT_CREATE_REQUEST_2 = {
    "agent_name": "Another Agent",
    "agent_architecture": "krishna-mini",
    "agent_provider": "Bedrock",
    "agent_provider_api_key": "another-api-key-456",
    "agent_persona": "You are another helpful assistant.",
}

# Conversation creation request data
CONVERSATION_CREATE_REQUEST = {
    "title": "Test Conversation",
    "description": "A test conversation for unit testing",
    "agent_id": "test-agent-id",
}

CONVERSATION_CREATE_REQUEST_2 = {
    "title": "Another Conversation",
    "description": "Another test conversation",
    "agent_id": "test-agent-id",
}

# API Key creation request data
API_KEY_CREATE_REQUEST = {
    "name": "Production Key",
    "allowed_origins": ["https://example.com", "https://app.example.com"],
}

API_KEY_CREATE_REQUEST_2 = {
    "name": "Development Key",
    "allowed_origins": [],
}

# Automation creation request data
AUTOMATION_CREATE_REQUEST = {
    "title": "Customer Follow-up",
    "description": "Draft a customer follow-up reply",
}

# DynamoDB table schema
DYNAMODB_TABLE_NAME = "test-table"

DYNAMODB_TABLE_SCHEMA = {
    "TableName": DYNAMODB_TABLE_NAME,
    "KeySchema": [
        {"AttributeName": "pk", "KeyType": "HASH"},
        {"AttributeName": "sk", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "pk", "AttributeType": "S"},
        {"AttributeName": "sk", "AttributeType": "S"},
        {"AttributeName": "gsi2_pk", "AttributeType": "S"},
        {"AttributeName": "gsi2_sk", "AttributeType": "S"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "gsi2",
            "KeySchema": [
                {"AttributeName": "gsi2_pk", "KeyType": "HASH"},
                {"AttributeName": "gsi2_sk", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


def test_owner(email: str = TEST_USER_EMAIL):
    """The seeded person as the `Owner` services take: in their personal account."""
    return owner_for(email)


def automation_fields(email: str = TEST_USER_EMAIL) -> dict:
    """The ownership fields an `Automation(...)` built in a test needs: like an agent's."""
    return agent_fields(email)


def schedule_fields(email: str = TEST_USER_EMAIL) -> dict:
    """The fields a `Schedule(...)` built in a test needs: run as `email`, in their personal account."""
    account_id, user_id = owner_ids(email)
    return {"account_id": account_id, "owner_id": user_id}


def session_fields(email: str = TEST_USER_EMAIL) -> dict:
    """The fields a `BuilderSession(...)` built in a test needs: the seeded person's, in their personal account."""
    account_id, user_id = owner_ids(email)
    return {"account_id": account_id, "user_id": user_id}


def turn_owner_fields(email: str = TEST_USER_EMAIL) -> dict:
    """What an `AgentTurnState(...)` built in a test needs for the member it runs as."""
    account_id, user_id = owner_ids(email)
    return {"account_id": account_id, "owner_id": user_id}
