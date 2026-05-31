from __future__ import annotations

from collections.abc import Callable

from src.messages.repositories.base import MessageRepository
from src.messages.repositories.dynamodb import DynamoDBMessageRepository
from src.messages.repositories.in_memory import InMemoryMessageRepository

_REPOSITORIES: dict[str, Callable[[], MessageRepository]] = {
    "dynamodb": DynamoDBMessageRepository,
    "in_memory": InMemoryMessageRepository,
}


def get_message_repository(name: str = "dynamodb") -> MessageRepository:
    try:
        return _REPOSITORIES[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown message repository: {name}") from exc
