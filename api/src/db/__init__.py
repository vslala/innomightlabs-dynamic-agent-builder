"""Database utilities and helpers."""

from .dynamodb import get_dynamodb_resource, get_dynamodb_client

__all__ = ["get_dynamodb_resource", "get_dynamodb_client"]
