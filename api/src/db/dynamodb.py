"""
DynamoDB connection helpers with support for local DynamoDB.

Usage:
    from src.db import get_dynamodb_resource

    class MyRepository:
        def __init__(self):
            self.dynamodb = get_dynamodb_resource()
            self.table = self.dynamodb.Table(settings.dynamodb_table)

Resources and clients are cached per thread. One chat turn constructs on the
order of fifteen repositories, and every uncached boto3 resource brings its own
urllib3 connection pool -- so DynamoDB calls could not reuse a keep-alive
connection between repositories and most paid a fresh TLS handshake. The cache
is per thread, not global, because boto3 resources are not documented
thread-safe and some repository work runs under `asyncio.to_thread`.
"""

import threading

import boto3

from src.config import settings

_local = threading.local()


def _connection_kwargs() -> dict[str, str]:
    kwargs = {"region_name": settings.aws_region}

    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
        kwargs["aws_access_key_id"] = "dummy"
        kwargs["aws_secret_access_key"] = "dummy"

    return kwargs


def get_dynamodb_resource():
    """
    Get a DynamoDB resource with automatic endpoint detection.

    - If DYNAMODB_ENDPOINT is set (e.g., http://localhost:8000), uses local DynamoDB
    - Otherwise, uses AWS DynamoDB in the configured region

    Returns:
        boto3.resource: DynamoDB resource instance, cached for this thread
    """
    resource = getattr(_local, "resource", None)
    if resource is None:
        resource = boto3.resource("dynamodb", **_connection_kwargs())
        _local.resource = resource
    return resource


def get_dynamodb_client():
    """
    Get a DynamoDB client with automatic endpoint detection.

    - If DYNAMODB_ENDPOINT is set (e.g., http://localhost:8000), uses local DynamoDB
    - Otherwise, uses AWS DynamoDB in the configured region

    Returns:
        boto3.client: DynamoDB client instance, cached for this thread
    """
    client = getattr(_local, "client", None)
    if client is None:
        client = boto3.client("dynamodb", **_connection_kwargs())
        _local.client = client
    return client


def reset_dynamodb_connections() -> None:
    """Drop this thread's cached connections.

    Tests need this: each one runs in its own `mock_aws` context, and a
    connection cached under a previous context must not be reused.
    """
    _local.resource = None
    _local.client = None
