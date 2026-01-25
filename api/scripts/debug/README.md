# Debug Scripts

Utility scripts for debugging and inspecting the database.

## check_user.py

Check if a user exists in the database and view their details.

### Usage

```bash
# Check specific user
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
uv run python scripts/debug/check_user.py testuser@example.com

# List all users in local database
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
uv run python scripts/debug/check_user.py --all

# Check user in production (careful!)
uv run python scripts/debug/check_user.py user@example.com
```

### Output

For a specific user:
```
Checking user: testuser@example.com
============================================================
✓ User found:
  Email: testuser@example.com
  Name: Test User
  Stripe Customer ID: cus_xxxxx
  Status: active
  Picture: https://...
  Created: 2026-01-25T12:00:00
  Updated: 2026-01-25T12:00:00
```

For all users:
```
Listing all users from: dynamic-agent-builder-local
Endpoint: http://localhost:8001
============================================================
Found 3 users:

  • testuser1@example.com
    Name: Test User 1
    Status: active
    Created: 2026-01-25T10:00:00
    Stripe: cus_xxxxx1

  • testuser2@example.com
    Name: Test User 2
    Status: active
    Created: 2026-01-25T11:00:00
```

## check_user_subscription.py

Check a user's subscription details.

```bash
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
uv run python scripts/debug/check_user_subscription.py testuser@example.com
```

## scan_db.py

Scan the entire database and show all items (use with caution).

```bash
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
uv run python scripts/debug/scan_db.py
```

## list_webhook_events.py

List recent webhook events.

```bash
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
uv run python scripts/debug/list_webhook_events.py
```

## Environment Variables

All scripts respect these environment variables:

- `DYNAMODB_ENDPOINT` - DynamoDB endpoint (use `http://localhost:8001` for local)
- `DYNAMODB_TABLE` - Table name (e.g., `dynamic-agent-builder-local`)
- `ENVIRONMENT` - Environment name (defaults to value in script)

## Tips

### Create Shell Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
alias check-user-local='DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local uv run python scripts/debug/check_user.py'
alias list-users-local='check-user-local --all'
```

Then use:
```bash
check-user-local testuser@example.com
list-users-local
```

### Quick Local Setup

If using local DynamoDB:

```bash
# In one terminal
docker-compose -f docker-compose.local.yml up

# In another terminal
export DYNAMODB_ENDPOINT=http://localhost:8001
export DYNAMODB_TABLE=dynamic-agent-builder-local
uv run python scripts/debug/check_user.py --all
```
