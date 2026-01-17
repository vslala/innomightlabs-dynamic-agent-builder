"""
Reusable mock data for tests.
"""

# Test user data
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_EMAIL_2 = "otheruser@example.com"

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
    ],
    "BillingMode": "PAY_PER_REQUEST",
}
