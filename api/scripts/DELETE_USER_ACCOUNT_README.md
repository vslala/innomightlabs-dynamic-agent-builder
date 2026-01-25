# User Account Deletion Script

Complete deletion of all user data following GDPR "right to be forgotten" requirements.

## ⚠️ Warning

**THIS IS A DESTRUCTIVE OPERATION THAT CANNOT BE UNDONE!**

This script will permanently delete ALL data associated with a user account including:
- User record
- All conversations and messages
- All agents and their memory/settings
- All knowledge bases and crawled content
- All subscriptions and billing records
- All usage tracking data
- All provider settings
- Everything else

## Features

✅ **Complete Deletion** - Follows entity hierarchy to delete all related data
✅ **Dry Run Mode** - Preview what will be deleted without actually deleting
✅ **Safety Confirmation** - Requires typing email to confirm
✅ **Detailed Logging** - Shows exactly what's being deleted
✅ **Batch Operations** - Efficient deletion using DynamoDB batch operations
✅ **Error Handling** - Continues on errors, reports what failed

## Deletion Hierarchy

The script deletes data in this order (children first):

```
1. Crawled Pages (CRAWL_JOB#{job_id} → PAGE#*)
2. Crawl Steps (CRAWL_JOB#{job_id} → STEP#*)
3. Crawl Jobs (KB#{kb_id} → CRAWL_JOB#*)
4. Content Chunks (KB#{kb_id} → CHUNK#*)
5. Knowledge Bases (USER#{email} → KB#*)
6. Widget Conversations (GSI2: AGENT#{agent_id} → WIDGET_CONVERSATION#*)
7. API Keys (GSI2: AGENT#{agent_id} → APIKEY#*)
8. Agent-KB Links (AGENT#{agent_id} → KB#*)
9. Agent Capacity Warnings (AGENT#{agent_id} → CAPACITY#*)
10. Agent Archival Memory (AGENT#{agent_id} → ARCHIVAL#*)
11. Agent Memory (AGENT#{agent_id} → MEMORY#*)
12. Agents (USER#{email} → AGENT#*)
13. Messages (CONVERSATION#{id} → MESSAGE#*)
14. Conversations (USER#{email} → CONVERSATION#*)
15. Webhook Events (USER#{email} → WEBHOOK_EVENT#*)
16. Email Events (USER#{email} → EMAIL_EVENT#*)
17. Usage Records (USER#{email} → USAGE#*)
18. Subscriptions (USER#{email} → SUBSCRIPTION#*)
19. Provider Settings (USER#{email} → PROVIDER#*)
20. User Record (USER#{email} → USER#{email})
```

## Usage

### 1. Dry Run (Recommended First Step)

**Always run in dry-run mode first** to see what would be deleted:

```bash
# Local DynamoDB
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
python scripts/delete_user_account.py testuser@example.com --dry-run

# Production (careful!)
python scripts/delete_user_account.py user@example.com --dry-run
```

Output:
```
🗑️  USER ACCOUNT DELETION TOOL
================================================================================

Target User: testuser@example.com
Mode: DRY RUN
Database: dynamic-agent-builder-local

🔎 Scanning for data associated with: testuser@example.com
================================================================================
  • Scanning User record...
  • Scanning Conversations...
  • Scanning Messages (2 conversations)...
  • Scanning Agents...
  • Scanning Agent-related data (3 agents)...
  • Scanning Knowledge Bases...
  • Scanning KB-related data (1 knowledge bases)...
  • Scanning Provider Settings...
  • Scanning Subscriptions...
  • Scanning Usage Records...
  • Scanning Email Events...
  • Scanning Webhook Events...

================================================================================
📊 DELETION SUMMARY for testuser@example.com
================================================================================
  • User......................................      1 items
  • Conversations.............................      2 items
  • Messages..................................     45 items
  • Agents....................................      3 items
  • Agent Memory..............................     12 items
  • Api Keys..................................      2 items
  • Knowledge Bases...........................      1 items
  • Content Chunks............................    150 items
  • Crawl Jobs................................      2 items
  • Crawled Pages.............................     28 items
  • Provider Settings.........................      2 items
  • Subscriptions.............................      1 items
  • Usage Records.............................      3 items
================================================================================
  TOTAL ITEMS TO DELETE.......................    252
================================================================================

🔎 DRY RUN COMPLETE - No data was deleted
   Run without --dry-run to actually delete this data
```

### 2. Actual Deletion (With Confirmation)

After reviewing the dry-run output:

```bash
# You will be prompted to type the email address to confirm
python scripts/delete_user_account.py user@example.com
```

You'll see:
```
================================================================================
⚠️  WARNING: THIS ACTION CANNOT BE UNDONE!
================================================================================

You are about to permanently delete ALL data for: user@example.com

This includes:
  • User account
  • All conversations and messages
  • All agents and their memory
  • All knowledge bases and content
  • All subscriptions and usage records
  • Everything else associated with this account

================================================================================

Type "user@example.com" to confirm deletion:
```

### 3. Skip Confirmation (Dangerous!)

Only use this for automation/scripts:

```bash
python scripts/delete_user_account.py user@example.com --yes
```

## Common Use Cases

### Local Testing - Delete Test User

```bash
cd api

# Dry run first
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
python scripts/delete_user_account.py testuser@example.com --dry-run

# Actually delete
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
python scripts/delete_user_account.py testuser@example.com
```

### Production - GDPR Request

```bash
cd api

# ALWAYS dry run first in production!
python scripts/delete_user_account.py user@example.com --dry-run

# Review the output carefully, then delete
python scripts/delete_user_account.py user@example.com
```

### Bulk Deletion (Multiple Users)

```bash
# Create a list of emails
cat > users_to_delete.txt <<EOF
user1@example.com
user2@example.com
user3@example.com
EOF

# Dry run for all
for email in $(cat users_to_delete.txt); do
    python scripts/delete_user_account.py "$email" --dry-run
done

# After reviewing, delete all
for email in $(cat users_to_delete.txt); do
    python scripts/delete_user_account.py "$email" --yes
done
```

## Output Interpretation

### Successful Deletion

```
🗑️  DELETING DATA (This cannot be undone!)
================================================================================

  Deleting Crawled Pages... (28 items)
    ✓ Deleted 28/28 Crawled Pages

  Deleting Crawl Steps... (15 items)
    ✓ Deleted 15/15 Crawl Steps

  ...

================================================================================
✅ DELETION COMPLETE
================================================================================

Deleted 252 total items
```

### Partial Failure

```
  Deleting Messages... (45 items)
    ✓ Deleted 25/45 Messages
    ✗ Error deleting batch: ProvisionedThroughputExceededException
    ✓ Deleted 45/45 Messages
```

The script will continue even if some batches fail. Review the output to see what was deleted.

## What Gets Deleted

| Entity Type | PK Pattern | SK Pattern | Notes |
|-------------|------------|------------|-------|
| User | `USER#{email}` | `USER#{email}` | Main user record |
| Conversations | `USER#{email}` | `CONVERSATION#{id}` | User's conversations |
| Messages | `CONVERSATION#{id}` | `MESSAGE#{ts}#{id}` | All messages in conversations |
| Agents | `USER#{email}` | `AGENT#{id}` | User's agents |
| Agent Memory | `AGENT#{id}` | `MEMORY#{block}` | Memory block definitions |
| Archival Memory | `AGENT#{id}` | `ARCHIVAL#{hash}` | Long-term memory |
| Capacity Warnings | `AGENT#{id}` | `CAPACITY#{date}` | Usage warnings |
| API Keys | GSI2 lookup | `APIKEY#{id}` | Agent API keys |
| Widget Conversations | GSI2 lookup | `WIDGET_CONVERSATION#{id}` | Widget chats |
| Agent-KB Links | `AGENT#{id}` | `KB#{kb_id}` | Agent knowledge base links |
| Knowledge Bases | `USER#{email}` | `KB#{id}` | User's knowledge bases |
| Content Chunks | `KB#{id}` | `CHUNK#{id}` | Embedded content |
| Crawl Jobs | `KB#{id}` | `CRAWL_JOB#{id}` | Crawling jobs |
| Crawl Steps | `CRAWL_JOB#{id}` | `STEP#{url}` | Individual crawl steps |
| Crawled Pages | `CRAWL_JOB#{id}` | `PAGE#{url_hash}` | Crawled page data |
| Provider Settings | `USER#{email}` | `PROVIDER#{name}` | LLM provider configs |
| Subscriptions | `USER#{email}` | `SUBSCRIPTION#{id}` | Stripe subscriptions |
| Usage Records | `USER#{email}` | `USAGE#{period}` | Monthly usage tracking |
| Email Events | `USER#{email}` | `EMAIL_EVENT#{id}` | Email delivery tracking |

## What Doesn't Get Deleted

These items exist outside the user's data scope:

- ❌ **Stripe Customer Records** - Must be handled via Stripe API separately
- ❌ **Vector Embeddings** - Pinecone vectors must be deleted separately
- ❌ **CloudWatch Logs** - Lambda execution logs remain
- ❌ **S3 Objects** - Any uploaded files in S3 buckets
- ❌ **ECR Images** - Docker images remain

### Complete GDPR Compliance

To fully comply with GDPR, also delete:

1. **Stripe Data**:
   ```bash
   stripe customers delete cus_XXXXX
   ```

2. **Pinecone Vectors**:
   ```python
   # Delete namespace or filter by user metadata
   index.delete(namespace=f"user_{user_id}")
   ```

3. **S3 Files** (if applicable):
   ```bash
   aws s3 rm s3://bucket-name/user-uploads/user@example.com/ --recursive
   ```

## Safety Features

### 1. Dry Run Mode
Always preview changes before deletion:
```bash
python scripts/delete_user_account.py user@example.com --dry-run
```

### 2. Email Confirmation
Must type exact email to confirm:
```
Type "user@example.com" to confirm deletion: user@example.com
```

### 3. Detailed Logging
See exactly what's being deleted in real-time

### 4. Batch Error Handling
Continues deleting even if some batches fail

### 5. No Accidental Execution
No default "yes" behavior without explicit flag

## Troubleshooting

### No Data Found

```
✓ No data found for user@example.com
```

**Causes**:
- Email doesn't exist in database
- Email format is different (check case sensitivity)
- Looking at wrong database (check DYNAMODB_TABLE)

**Solution**:
```bash
# List all users
python scripts/debug/scan_db.py | grep "USER#"
```

### ProvisionedThroughputExceededException

```
✗ Error deleting batch: ProvisionedThroughputExceededException
```

**Cause**: Too many delete operations at once

**Solution**:
- Wait a few minutes and run again
- The script will continue and retry failed batches
- Increase DynamoDB provisioned throughput (production)

### Partial Deletion

If the script crashes mid-deletion, re-run it:
```bash
python scripts/delete_user_account.py user@example.com
```

It will only delete remaining items (idempotent).

### Wrong User Deleted

**There is no undo!** However, if you have:

1. **Database Backups**: Restore from DynamoDB backup
2. **Point-in-Time Recovery**: Restore to time before deletion
3. **Application Logs**: Might be able to reconstruct some data

**Prevention**: Always use `--dry-run` first!

## Performance

- Deletes in batches of 25 items (DynamoDB limit)
- Typical performance: ~100 items/second
- 1,000 items ≈ 10 seconds
- 10,000 items ≈ 100 seconds

## Integration with Application

### Add to Admin Panel

```python
from scripts.delete_user_account import UserAccountDeleter

def delete_user_account(email: str):
    """Admin endpoint to delete user account."""
    deleter = UserAccountDeleter(email, dry_run=False)
    all_data = deleter.scan_user_data()
    return deleter.delete_all_data(all_data)
```

### Background Job

```python
# Celery task for async deletion
@celery.task
def delete_user_account_async(email: str):
    deleter = UserAccountDeleter(email, dry_run=False)
    all_data = deleter.scan_user_data()
    deleter.delete_all_data(all_data)

    # Notify user
    send_email(email, "Account Deletion Complete", "Your data has been removed.")
```

## Legal Compliance

### GDPR Article 17 - Right to Erasure

This script helps comply with GDPR's "right to be forgotten" by:

✅ Deleting all personal data
✅ Deleting derived data (usage stats, etc.)
✅ Providing deletion audit trail (logs)
✅ Completing deletion within 30 days

**Note**: You must also delete data in third-party systems (Stripe, Pinecone, etc.)

### CCPA Compliance

Similar requirements to GDPR. This script covers the database portion.

## Testing

### Test with Local DynamoDB

```bash
# Start local DynamoDB
docker-compose -f docker-compose.local.yml up -d

# Create test user
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
python scripts/create_test_user.py testuser@example.com

# Delete test user
DYNAMODB_ENDPOINT=http://localhost:8001 \
DYNAMODB_TABLE=dynamic-agent-builder-local \
python scripts/delete_user_account.py testuser@example.com --dry-run
```

### Integration Tests

Add to test suite:
```python
def test_user_deletion():
    # Create test user with data
    create_test_user("test@example.com")

    # Delete
    deleter = UserAccountDeleter("test@example.com")
    all_data = deleter.scan_user_data()
    deleter.delete_all_data(all_data)

    # Verify deletion
    remaining = deleter.scan_user_data()
    assert sum(len(v) for v in remaining.values()) == 0
```

## Support

If you encounter issues:

1. Check the logs carefully
2. Try dry-run mode first
3. Verify database connection
4. Check AWS IAM permissions
5. Review this README

For bugs or improvements, update this script as needed.
