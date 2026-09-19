"""Connection reuse for DynamoDB.

Every uncached boto3 resource brings its own urllib3 connection pool, so the
~15 repositories one chat turn constructs could not share a keep-alive
connection. See api/docs/LLD-agent-runtime-refactor.md (P1.5).
"""

import threading

from src.db import get_dynamodb_client, get_dynamodb_resource, reset_dynamodb_connections


def test_repeated_calls_on_one_thread_reuse_the_same_connection(dynamodb_table):
    assert get_dynamodb_resource() is get_dynamodb_resource()
    assert get_dynamodb_client() is get_dynamodb_client()


def test_each_thread_gets_its_own_connection(dynamodb_table):
    """boto3 resources are not documented thread-safe, and some repository work
    runs under asyncio.to_thread."""
    main = get_dynamodb_resource()
    from_worker = []

    worker = threading.Thread(target=lambda: from_worker.append(get_dynamodb_resource()))
    worker.start()
    worker.join()

    assert from_worker[0] is not main


def test_resetting_drops_the_cached_connection(dynamodb_table):
    first = get_dynamodb_resource()
    reset_dynamodb_connections()

    assert get_dynamodb_resource() is not first


def test_repositories_built_separately_share_one_connection(dynamodb_table):
    from src.agents.turns.repository import ConversationTurnRepository
    from src.conversations.repository import ConversationRepository
    from src.messages.repositories.dynamodb import DynamoDBMessageRepository

    repositories = [
        ConversationRepository(),
        ConversationTurnRepository(),
        DynamoDBMessageRepository(),
    ]

    assert len({id(repo.dynamodb) for repo in repositories}) == 1
