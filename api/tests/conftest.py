"""
Pytest fixtures for tests.
"""

import os

# Set environment variables BEFORE any other imports
# This ensures settings module loads with test values
os.environ["DYNAMODB_TABLE"] = "test-table"
os.environ["AWS_REGION_NAME"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["JWT_SECRET"] = "test-secret"
os.environ.pop("DYNAMODB_ENDPOINT", None)

import pytest
import boto3
from moto import mock_aws
from fastapi.testclient import TestClient

from tests.mock_data import (
    DYNAMODB_TABLE_NAME,
    DYNAMODB_TABLE_SCHEMA,
    TEST_USER_EMAIL,
)


@pytest.fixture
def mock_aws_context():
    """Create a mocked AWS context for all tests."""
    with mock_aws():
        yield


@pytest.fixture
def dynamodb_table(mock_aws_context):
    """Create a mocked DynamoDB table."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(**DYNAMODB_TABLE_SCHEMA)
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    # Wait for table to be active
    table.meta.client.get_waiter('table_exists').wait(TableName=DYNAMODB_TABLE_NAME)
    return table


@pytest.fixture
def agent_repository(dynamodb_table):
    """Create AgentRepository with mocked DynamoDB."""
    # Import here to ensure settings are loaded with test env vars
    from src.agents.repository import AgentRepository
    # Create new instance to ensure it uses the mock
    return AgentRepository()


@pytest.fixture
def conversation_repository(dynamodb_table):
    """Create ConversationRepository with mocked DynamoDB."""
    from src.conversations.repository import ConversationRepository
    return ConversationRepository()


@pytest.fixture
def test_client(dynamodb_table):
    """Create FastAPI test client with mocked DynamoDB."""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Generate valid auth headers for testing."""
    import jwt
    from datetime import datetime, timedelta, timezone

    token = jwt.encode(
        {
            "sub": TEST_USER_EMAIL,
            "name": "Test User",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
