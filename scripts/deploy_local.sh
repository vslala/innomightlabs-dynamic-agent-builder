#!/usr/bin/env bash
# This script should be SOURCED, not executed
# Usage: source scripts/deploy_local.sh
# or:    . scripts/deploy_local.sh

# Detect if script is being sourced or executed
is_sourced() {
  if [[ -n "${ZSH_EVAL_CONTEXT:-}" ]]; then
    [[ "$ZSH_EVAL_CONTEXT" == *:file ]]
    return
  fi
  if [[ -n "${BASH_SOURCE:-}" ]]; then
    [[ "${BASH_SOURCE[0]}" != "${0}" ]]
    return
  fi
  return 1
}

if ! is_sourced; then
  echo "❌ Error: This script must be sourced, not executed."
  echo "Usage: source scripts/deploy_local.sh"
  echo "   or: . scripts/deploy_local.sh"
  exit 1
fi

# Get the script directory (works in both bash and zsh when sourced)
if [[ -n "${BASH_SOURCE:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
else
  echo "❌ Error: Unable to determine script directory"
  return 1
fi

PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Setting up LOCAL development environment"
echo "=========================================="
echo ""

# Source .envrc to get all environment variables
if [[ -f "$PROJECT_ROOT/.envrc" ]]; then
  source "$PROJECT_ROOT/.envrc"
else
  echo "❌ Error: .envrc file not found at $PROJECT_ROOT/.envrc"
  return 1
fi

# Set environment variables from LOCAL_ prefixed variables
export ENVIRONMENT="${LOCAL_ENVIRONMENT}"
export FRONTEND_URL="${LOCAL_FRONTEND_URL}"
export API_DOMAIN="${LOCAL_API_DOMAIN}"
export API_BASE_URL="${LOCAL_API_DOMAIN}"
export VITE_API_BASE_URL="${LOCAL_API_DOMAIN}"
export SPA_PORT="${LOCAL_SPA_PORT}"
export WIDGET_CDN_DOMAIN="${LOCAL_WIDGET_CDN_DOMAIN}"
export GOOGLE_CLIENT_ID="${LOCAL_GOOGLE_CLIENT_ID}"
export GOOGLE_CLIENT_SECRET="${LOCAL_GOOGLE_CLIENT_SECRET}"
export JWT_SECRET="${LOCAL_JWT_SECRET}"
export COGNITO_DOMAIN_PREFIX="${LOCAL_COGNITO_DOMAIN_PREFIX}"
export COGNITO_CALLBACK_URLS="${LOCAL_COGNITO_CALLBACK_URLS}"
export COGNITO_LOGOUT_URLS="${LOCAL_COGNITO_LOGOUT_URLS}"
export COGNITO_REDIRECT_URI="${LOCAL_COGNITO_REDIRECT_URI}"
export OPENAI_OAUTH_CLIENT_ID="${LOCAL_OPENAI_OAUTH_CLIENT_ID:-${OPENAI_OAUTH_CLIENT_ID}}"
export OPENAI_OAUTH_SCOPES="${LOCAL_OPENAI_OAUTH_SCOPES:-${OPENAI_OAUTH_SCOPES}}"
export OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS="${LOCAL_OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS:-${OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS}}"
export OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW="${LOCAL_OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW:-${OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW}}"
export OPENAI_OAUTH_ORIGINATOR="${LOCAL_OPENAI_OAUTH_ORIGINATOR:-${OPENAI_OAUTH_ORIGINATOR}}"
export OPENAI_OAUTH_REDIRECT_URI="${LOCAL_OPENAI_OAUTH_REDIRECT_URI:-${OPENAI_OAUTH_REDIRECT_URI}}"
export SUPERUSER_EMAILS="${LOCAL_SUPERUSER_EMAILS:-${SUPERUSER_EMAILS}}"
export STRIPE_SECRET_KEY="${LOCAL_STRIPE_SECRET_KEY}"
export STRIPE_PUBLISHABLE_KEY="${LOCAL_STRIPE_PUBLISHABLE_KEY}"
export STRIPE_WEBHOOK_SECRET="${LOCAL_STRIPE_WEBHOOK_SECRET}"
export SES_DOMAIN="${LOCAL_SES_DOMAIN}"
export SES_FROM_EMAIL="${LOCAL_SES_FROM_EMAIL}"
export SES_REPLY_TO_EMAIL="${LOCAL_SES_REPLY_TO_EMAIL}"
export SES_VERIFICATION_EMAIL="${LOCAL_SES_VERIFICATION_EMAIL}"

# Also export common variables
export AWS_REGION="${AWS_REGION}"
export AWS_PROFILE="${AWS_PROFILE}"
export DYNAMODB_TABLE="${DYNAMODB_TABLE}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
export PINECONE_API_KEY="${PINECONE_API_KEY}"
export PINECONE_HOST="${PINECONE_HOST}"
export PINECONE_INDEX="${PINECONE_INDEX}"
export PRICING_CONFIG_PATH="${PRICING_CONFIG_PATH}"
export STRIPE_CURRENCY="${STRIPE_CURRENCY}"
export STRIPE_PRICE_STARTER_MONTHLY="${STRIPE_PRICE_STARTER_MONTHLY}"
export STRIPE_PRICE_STARTER_ANNUAL="${STRIPE_PRICE_STARTER_ANNUAL}"
export STRIPE_PRICE_PRO_MONTHLY="${STRIPE_PRICE_PRO_MONTHLY}"
export STRIPE_PRICE_PRO_ANNUAL="${STRIPE_PRICE_PRO_ANNUAL}"

echo "✅ Environment variables set for LOCAL development"
echo ""
echo "Key variables:"
echo "  ENVIRONMENT: $ENVIRONMENT"
echo "  FRONTEND_URL: $FRONTEND_URL"
echo "  API_DOMAIN: $API_DOMAIN"
echo "  AWS_REGION: $AWS_REGION"
echo ""
echo "You can now run: cd api && uv run uvicorn main:app --reload"
