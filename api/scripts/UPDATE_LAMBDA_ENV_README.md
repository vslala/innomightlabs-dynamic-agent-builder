# Lambda Environment Variable Update Script

## Problem

When deploying with Terraform, changing the `environment` variable from `dev` to `prod` causes:

1. **Tag updates** on all resources (just metadata - safe)
2. **Cognito User Pool recreation** - because the name changes from `dynamic-agent-builder-dev-user-pool` to `dynamic-agent-builder-prod-user-pool`
3. **Cascade recreation** of Cognito User Pool Client and Domain (depend on pool ID)
4. **Lambda environment variable updates** - the actual change we want

**Issue**: Recreating Cognito destroys all users and requires reconfiguring OAuth integrations!

## Solution

Use `update_lambda_env_prod.sh` to update **only** Lambda environment variables without touching infrastructure.

## Usage

```bash
# Make sure you're in the api directory
cd api

# Run the script (uses AWS_PROFILE=vslala by default)
./scripts/update_lambda_env_prod.sh

# Or specify a different profile
AWS_PROFILE=myprofile ./scripts/update_lambda_env_prod.sh
```

## What the Script Does

1. Reads configuration from `terraform/terraform.tfvars`
2. Extracts: `environment`, `stripe_secret_key`, `stripe_publishable_key`, `stripe_webhook_secret`
3. Updates Lambda functions:
   - `dynamic-agent-builder-api` (main API)
   - `dynamic-agent-builder-usage-events` (DynamoDB stream handler)
4. Preserves all other environment variables
5. Waits for functions to be ready

## Preventing Cognito Recreation in Terraform

### Option 1: Use Same Name for All Environments (Recommended)

In `terraform/main.tf`, change the Cognito user pool name to not include environment:

```hcl
resource "aws_cognito_user_pool" "main" {
  name = "dynamic-agent-builder-user-pool"  # Remove "-${var.environment}"
  # ... rest of config
}

resource "aws_cognito_user_pool_client" "hosted_ui" {
  name         = "dynamic-agent-builder-web-client"  # Remove "-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id
  # ... rest of config
}
```

**Pros**: Single Cognito pool for all environments, no recreation needed
**Cons**: All environments share the same user pool (usually fine for most use cases)

### Option 2: Use Lifecycle Ignore Changes

If you must have separate user pools per environment, use `lifecycle` rules:

```hcl
resource "aws_cognito_user_pool" "main" {
  name = "dynamic-agent-builder-${var.environment}-user-pool"

  lifecycle {
    ignore_changes = [
      name,  # Ignore name changes to prevent recreation
    ]
  }

  # ... rest of config
}
```

**Pros**: Prevents recreation when environment changes
**Cons**: Name won't update even if you want it to

### Option 3: Separate State Files Per Environment

Use workspace-specific state files:

```bash
# For dev
terraform workspace select dev
terraform apply

# For prod
terraform workspace select prod
terraform apply
```

**Pros**: Complete isolation between environments
**Cons**: More complex state management

## Recommended Approach for This Project

Since you're using the same AWS account for both dev and prod, and the infrastructure is mostly identical:

1. **For Lambda env vars**: Use this script (`update_lambda_env_prod.sh`)
2. **For Cognito**: Use Option 1 (same name, no environment suffix)
3. **For tags**: Let Terraform update them (they're just metadata)

This way:
- ✅ Infrastructure remains stable
- ✅ Lambda env vars can be updated quickly
- ✅ No user data loss
- ✅ Simple deployment process

## Verifying Changes

After running the script, verify the changes:

```bash
# Check main API Lambda
aws lambda get-function-configuration \
  --function-name dynamic-agent-builder-api \
  --region us-east-1 \
  --profile vslala \
  --query 'Environment.Variables' \
  --output json

# Check usage events Lambda
aws lambda get-function-configuration \
  --function-name dynamic-agent-builder-usage-events \
  --region us-east-1 \
  --profile vslala \
  --query 'Environment.Variables' \
  --output json
```

## When to Use Terraform vs This Script

| Change Type | Use Terraform | Use Script |
|-------------|---------------|------------|
| New Lambda function | ✅ | ❌ |
| Lambda code update | ✅ | ❌ |
| Lambda memory/timeout | ✅ | ❌ |
| Lambda env vars only | ❌ | ✅ |
| API Gateway changes | ✅ | ❌ |
| DynamoDB schema | ✅ | ❌ |
| IAM permissions | ✅ | ❌ |
| Quick env var fix | ❌ | ✅ |

## Troubleshooting

### Script fails with "function not found"
- Check Lambda function names match: `dynamic-agent-builder-api` and `dynamic-agent-builder-usage-events`
- Verify AWS profile and region are correct

### Stripe keys not updating
- Ensure keys are in `terraform/terraform.tfvars`
- Check the tfvars file format (should be `key = "value"`)

### Functions not ready after update
- Wait a minute and try again
- Check CloudWatch logs for any errors

### Want to revert changes
```bash
# Get previous environment config
aws lambda get-function-configuration \
  --function-name dynamic-agent-builder-api \
  --region us-east-1 \
  --profile vslala

# Manually update with previous values
aws lambda update-function-configuration \
  --function-name dynamic-agent-builder-api \
  --region us-east-1 \
  --profile vslala \
  --environment 'Variables={ENVIRONMENT=dev,...}'
```

## Future Improvements

Consider these enhancements:

1. **Config file**: Read from a JSON config instead of tfvars
2. **Rollback**: Keep previous config for easy rollback
3. **Validation**: Check API health after update
4. **Multiple environments**: Support updating multiple environments at once
5. **Dry run**: Show what would change without applying
