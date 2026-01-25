"""
DynamoDB connection helpers with support for local DynamoDB.

Usage:
    from src.db import get_dynamodb_resource

    class MyRepository:
        def __init__(self):
            self.dynamodb = get_dynamodb_resource()
            self.table = self.dynamodb.Table(settings.dynamodb_table)
"""

import boto3
from src.config import settings


def get_dynamodb_resource():
    """
    Get a DynamoDB resource with automatic endpoint detection.

    - If DYNAMODB_ENDPOINT is set (e.g., http://localhost:8000), uses local DynamoDB
    - Otherwise, uses AWS DynamoDB in the configured region

    Returns:
        boto3.resource: DynamoDB resource instance
    """
    kwargs = {"region_name": settings.aws_region}

    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint

    return boto3.resource("dynamodb", **kwargs)


def get_dynamodb_client():
    """
    Get a DynamoDB client with automatic endpoint detection.

    - If DYNAMODB_ENDPOINT is set (e.g., http://localhost:8000), uses local DynamoDB
    - Otherwise, uses AWS DynamoDB in the configured region

    Returns:
        boto3.client: DynamoDB client instance
    """
    kwargs = {"region_name": settings.aws_region}

    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint

    return boto3.client("dynamodb", **kwargs)
