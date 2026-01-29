#!/usr/bin/env python3
"""
Initialize local DynamoDB table with the same schema as production.

Usage:
    python scripts/init_local_dynamodb.py
"""

import boto3
from botocore.exceptions import ClientError
import os

# Local DynamoDB configuration
ENDPOINT_URL = "http://localhost:8001"
REGION = os.getenv("AWS_REGION_NAME", "us-east-1")
TABLE_NAME = "dynamic-agent-builder-local"


def create_table():
    """Create the DynamoDB table with the same schema as production."""
    dynamodb = boto3.client(
        "dynamodb",
        endpoint_url=ENDPOINT_URL,
        region_name=REGION,
        # Credentials are ignored by DynamoDB Local but required by boto3
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
    )

    try:
        # Check if table already exists
        dynamodb.describe_table(TableName=TABLE_NAME)
        print(f"✓ Table '{TABLE_NAME}' already exists")
        return
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code != "ResourceNotFoundException":
            raise

    # Create table with the same schema as production
    print(f"Creating table '{TABLE_NAME}'...")
    dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "entity_type", "AttributeType": "S"},
            {"AttributeName": "user_email", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "gsi2_pk", "AttributeType": "S"},
            {"AttributeName": "gsi2_sk", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "EntityTypeIndex",
                "KeySchema": [
                    {"AttributeName": "entity_type", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            },
            {
                "IndexName": "UserEmailIndex",
                "KeySchema": [
                    {"AttributeName": "user_email", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            },
            {
                "IndexName": "gsi2",
                "KeySchema": [
                    {"AttributeName": "gsi2_pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi2_sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            },
        ],
        BillingMode="PROVISIONED",
        ProvisionedThroughput={
            "ReadCapacityUnits": 5,
            "WriteCapacityUnits": 5,
        },
    )

    # Wait for table to be created
    waiter = dynamodb.get_waiter("table_exists")
    waiter.wait(TableName=TABLE_NAME)

    print(f"✓ Table '{TABLE_NAME}' created successfully")


if __name__ == "__main__":
    try:
        create_table()
        print("\n✓ Local DynamoDB setup complete!")
        print(f"\nNext steps:")
        print(f"1. Set environment variable: export DYNAMODB_ENDPOINT=http://localhost:8001")
        print(f"2. Set table name: export DYNAMODB_TABLE={TABLE_NAME}")
        print(f"3. Start your API: uv run uvicorn main:app --reload")
    except Exception as e:
        print(f"✗ Error: {e}")
        exit(1)
