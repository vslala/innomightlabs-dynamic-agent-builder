#!/bin/bash
set -e

# Script to update Lambda environment variables for production
# This updates only environment variables without recreating infrastructure

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Updating Lambda Environment Variables for Production${NC}"
echo "================================================"

# Check if running with correct profile
AWS_PROFILE="${AWS_PROFILE:-vslala}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo -e "${YELLOW}Using AWS Profile:${NC} $AWS_PROFILE"
echo -e "${YELLOW}Using AWS Region:${NC} $AWS_REGION"
echo ""

# Read environment-specific variables from terraform.tfvars
TFVARS_FILE="$TERRAFORM_DIR/terraform.tfvars"

if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${RED}❌ Error: terraform.tfvars not found at $TFVARS_FILE${NC}"
    exit 1
fi

echo -e "${YELLOW}📖 Reading configuration from terraform.tfvars...${NC}"

# Extract values from tfvars (handling both quoted and unquoted values)
extract_tfvar() {
    local var_name=$1
    local value=$(grep "^${var_name}" "$TFVARS_FILE" | sed 's/^[^=]*=[[:space:]]*"\?\([^"]*\)"\?$/\1/' | tr -d '\r\n')
    echo "$value"
}

ENVIRONMENT=$(extract_tfvar "environment")
STRIPE_SECRET_KEY=$(extract_tfvar "stripe_secret_key")
STRIPE_PUBLISHABLE_KEY=$(extract_tfvar "stripe_publishable_key")
STRIPE_WEBHOOK_SECRET=$(extract_tfvar "stripe_webhook_secret")

# Validate required variables
if [ -z "$ENVIRONMENT" ]; then
    echo -e "${RED}❌ Error: environment not found in terraform.tfvars${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Environment:${NC} $ENVIRONMENT"
echo ""

# Function to update Lambda environment variables
update_lambda_env() {
    local function_name=$1
    local env_updates=$2

    echo -e "${YELLOW}📝 Updating $function_name...${NC}"

    # Get current environment variables
    CURRENT_ENV=$(aws lambda get-function-configuration \
        --function-name "$function_name" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'Environment.Variables' \
        --output json)

    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to get current environment for $function_name${NC}"
        return 1
    fi

    # Merge current environment with updates
    UPDATED_ENV=$(echo "$CURRENT_ENV" | jq ". + $env_updates")

    # Update Lambda function
    aws lambda update-function-configuration \
        --function-name "$function_name" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --environment "Variables=$UPDATED_ENV" \
        --output json > /dev/null

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully updated $function_name${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed to update $function_name${NC}"
        return 1
    fi
}

# Update main API Lambda
echo ""
echo "================================================"
echo -e "${GREEN}1. Updating Main API Lambda${NC}"
echo "================================================"

API_LAMBDA_NAME="dynamic-agent-builder-api"

# Prepare environment variable updates for main API
API_ENV_UPDATES=$(cat <<EOF
{
  "ENVIRONMENT": "$ENVIRONMENT"
}
EOF
)

# Add Stripe keys if provided
if [ -n "$STRIPE_SECRET_KEY" ]; then
    API_ENV_UPDATES=$(echo "$API_ENV_UPDATES" | jq ". + {\"STRIPE_SECRET_KEY\": \"$STRIPE_SECRET_KEY\"}")
fi

if [ -n "$STRIPE_PUBLISHABLE_KEY" ]; then
    API_ENV_UPDATES=$(echo "$API_ENV_UPDATES" | jq ". + {\"STRIPE_PUBLISHABLE_KEY\": \"$STRIPE_PUBLISHABLE_KEY\"}")
fi

if [ -n "$STRIPE_WEBHOOK_SECRET" ]; then
    API_ENV_UPDATES=$(echo "$API_ENV_UPDATES" | jq ". + {\"STRIPE_WEBHOOK_SECRET\": \"$STRIPE_WEBHOOK_SECRET\"}")
fi

update_lambda_env "$API_LAMBDA_NAME" "$API_ENV_UPDATES"

# Update usage events Lambda
echo ""
echo "================================================"
echo -e "${GREEN}2. Updating Usage Events Lambda${NC}"
echo "================================================"

USAGE_LAMBDA_NAME="dynamic-agent-builder-usage-events"

# Prepare environment variable updates for usage events
USAGE_ENV_UPDATES=$(cat <<EOF
{
  "ENVIRONMENT": "$ENVIRONMENT"
}
EOF
)

# Add Stripe secret key if provided
if [ -n "$STRIPE_SECRET_KEY" ]; then
    USAGE_ENV_UPDATES=$(echo "$USAGE_ENV_UPDATES" | jq ". + {\"STRIPE_SECRET_KEY\": \"$STRIPE_SECRET_KEY\"}")
fi

update_lambda_env "$USAGE_LAMBDA_NAME" "$USAGE_ENV_UPDATES"

# Wait for functions to be ready
echo ""
echo "================================================"
echo -e "${YELLOW}⏳ Waiting for Lambda functions to be ready...${NC}"
echo "================================================"

for lambda_name in "$API_LAMBDA_NAME" "$USAGE_LAMBDA_NAME"; do
    echo -e "${YELLOW}Waiting for $lambda_name...${NC}"
    aws lambda wait function-updated \
        --function-name "$lambda_name" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $lambda_name is ready${NC}"
    else
        echo -e "${YELLOW}⚠ Timeout waiting for $lambda_name (it may still be updating)${NC}"
    fi
done

echo ""
echo "================================================"
echo -e "${GREEN}✅ Lambda Environment Variables Updated Successfully!${NC}"
echo "================================================"
echo ""
echo -e "${YELLOW}📝 Summary:${NC}"
echo "  - Environment: $ENVIRONMENT"
echo "  - Updated Functions:"
echo "    • $API_LAMBDA_NAME"
echo "    • $USAGE_LAMBDA_NAME"
echo ""
echo -e "${YELLOW}🔍 Verification:${NC}"
echo "  Run the following to verify:"
echo "  aws lambda get-function-configuration --function-name $API_LAMBDA_NAME --region $AWS_REGION --profile $AWS_PROFILE --query 'Environment.Variables.ENVIRONMENT'"
echo ""
