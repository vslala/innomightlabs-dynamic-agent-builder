# Debug Scripts

Collection of debug scripts for inspecting database state and troubleshooting issues.

## Prerequisites

These scripts work with both local DynamoDB and AWS DynamoDB. Set environment variables to control which database to use:

```bash
# For local DynamoDB
export DYNAMODB_ENDPOINT=http://localhost:8001
export DYNAMODB_TABLE=dynamic-agent-builder-local

# For AWS DynamoDB (default)
# Just don't set DYNAMODB_ENDPOINT
export DYNAMODB_TABLE=dynamic-agent-builder-main
```

## Available Scripts

### 1. Check User Subscription

Check subscription details for a specific user:

```bash
# Basic usage
uv run python scripts/debug/check_user_subscription.py testuser@example.com

# With local DynamoDB
DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
    uv run python scripts/debug/check_user_subscription.py testuser@example.com
```

**Output:**
- Subscription ID
- Plan name (starter, pro, etc.)
- Status (active, canceled, etc.)
- Billing period dates
- Cancellation status

### 2. Check User

Check user details from database:

```bash
uv run python scripts/debug/check_user.py testuser@example.com
```

**Output:**
- User email and name
- Stripe customer ID
- Account status
- Creation/update timestamps
- TTL (for local dev users)

### 3. Scan Database

Get overview of what's in the database:

```bash
# Show counts only
uv run python scripts/debug/scan_db.py

# Show all items (verbose)
uv run python scripts/debug/scan_db.py --verbose
```

**Output:**
- Total item count
- Breakdown by entity type (User, Subscription, WebhookEvent, etc.)
- With `--verbose`: full list of all items

### 4. List Webhook Events

Show recent webhook events:

```bash
# Show last 10 (default)
uv run python scripts/debug/list_webhook_events.py

# Show last 20
uv run python scripts/debug/list_webhook_events.py --limit 20
```

**Output:**
- Event IDs
- Event types
- Timestamps

## Common Use Cases

### Troubleshooting Subscription Issues

1. **Check if user exists:**
   ```bash
   uv run python scripts/debug/check_user.py user@example.com
   ```

2. **Check subscription status:**
   ```bash
   uv run python scripts/debug/check_user_subscription.py user@example.com
   ```

3. **Verify webhook processing:**
   ```bash
   uv run python scripts/debug/list_webhook_events.py
   ```

### Debugging Local Development

When using local DynamoDB, always prefix commands with environment variables:

```bash
DYNAMODB_ENDPOINT=http://localhost:8001 DYNAMODB_TABLE=dynamic-agent-builder-local \
    uv run python scripts/debug/check_user_subscription.py testuser@example.com
```

Or export them once:
```bash
export DYNAMODB_ENDPOINT=http://localhost:8001
export DYNAMODB_TABLE=dynamic-agent-builder-local

# Now all scripts use local DB
uv run python scripts/debug/scan_db.py
uv run python scripts/debug/check_user.py testuser@example.com
```

## Tips

- **Use `scan_db.py` first** to get an overview of what's in the database
- **Check user before subscription** to ensure the user record exists
- **Use `--verbose` mode** on scan_db.py to see detailed item data
- **Check webhook events** if subscriptions aren't being created after checkout
