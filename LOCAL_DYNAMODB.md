# Local DynamoDB Setup

This guide explains how to use local DynamoDB for development and testing, keeping your test data separate from AWS.

## Quick Start

### 1. Start Local DynamoDB

```bash
docker-compose -f docker-compose.local.yml up -d
```

This starts DynamoDB Local on `http://localhost:8001`.

### 2. Initialize the Table

```bash
cd api
python scripts/init_local_dynamodb.py
```

This creates a table named `dynamic-agent-builder-local` with the same schema as production.

### 3. Configure Environment Variables

Create or update your `.env` file in the `api/` directory:

```bash
# Point to local DynamoDB
DYNAMODB_ENDPOINT=http://localhost:8001
DYNAMODB_TABLE=dynamic-agent-builder-local

# Keep other settings as usual
ENVIRONMENT=dev
AWS_REGION_NAME=eu-west-2
# ... other vars
```

### 4. Start the API

```bash
cd api
uv run uvicorn main:app --reload
```

Your API will now use local DynamoDB instead of AWS!

## How It Works

When `DYNAMODB_ENDPOINT` is set, all repository classes automatically use the local DynamoDB:

```python
# In src/db/dynamodb.py
def get_dynamodb_resource():
    kwargs = {"region_name": settings.aws_region}

    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint

    return boto3.resource("dynamodb", **kwargs)
```

All repositories use this helper function, so **no code changes** are needed to switch between local and AWS DynamoDB.

## Benefits

1. **Isolated Testing**: Test data stays local, never touches AWS
2. **Faster Development**: No network latency to AWS
3. **Cost Savings**: No AWS charges for local testing
4. **Offline Development**: Work without internet connection
5. **Auto-Cleanup**: Local test users with TTL expire automatically

## Local Auth Users

When using local authentication (`username@example.com`):
- Users are stored in local DynamoDB
- TTL automatically deletes them after 7 days
- No AWS charges or data retention concerns

## Switching Back to AWS

Simply remove or comment out the environment variable:

```bash
# .env
# DYNAMODB_ENDPOINT=http://localhost:8001  # Comment this out
```

Or unset it:

```bash
unset DYNAMODB_ENDPOINT
```

## Data Persistence

By default, local DynamoDB data is persisted in `./dynamodb-data/`. To start fresh:

```bash
docker-compose -f docker-compose.local.yml down
rm -rf dynamodb-data
docker-compose -f docker-compose.local.yml up -d
python scripts/init_local_dynamodb.py
```

## Troubleshooting

### Table Already Exists Error

If you see "Table already exists", you can either:
1. Use the existing table (skip init script)
2. Delete and recreate:

```bash
docker-compose -f docker-compose.local.yml down
rm -rf dynamodb-data
docker-compose -f docker-compose.local.yml up -d
python scripts/init_local_dynamodb.py
```

### Connection Refused

Ensure Docker container is running:

```bash
docker ps | grep dynamodb-local
```

If not running:

```bash
docker-compose -f docker-compose.local.yml up -d
```

### AWS Credentials Error with Local DynamoDB

DynamoDB Local doesn't validate credentials, but boto3 requires them. The init script uses dummy credentials (`aws_access_key_id="dummy"`), which is normal for local development.

## Viewing Local Data

Use AWS CLI with local endpoint:

```bash
aws dynamodb scan \
  --table-name dynamic-agent-builder-local \
  --endpoint-url http://localhost:8001 \
  --region eu-west-2 \
  --no-sign-request
```

Or use a GUI tool like [NoSQL Workbench](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/workbench.html).
