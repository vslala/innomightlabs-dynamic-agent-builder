#!/usr/bin/env bash
# This script should be SOURCED, not executed
# Usage: source scripts/deploy_local.sh
# or:    . scripts/deploy_local.sh

# Detect if script is being sourced or executed
is_sourced() {
  if [[ -n "${ZSH_EVAL_CONTEXT:-}" ]]; then
    case "$ZSH_EVAL_CONTEXT" in
      *:file|*:file:*) return 0 ;;
      *) return 1 ;;
    esac
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
  SKIP_DEFAULT_ENV=1 source "$PROJECT_ROOT/.envrc"
else
  echo "❌ Error: .envrc file not found at $PROJECT_ROOT/.envrc"
  return 1
fi

get_var() {
  local var_name="$1"
  local env_var="LOCAL_${var_name}"
  local value

  eval "value=\${$env_var:-}"

  if [[ -z "$value" ]]; then
    eval "value=\${$var_name:-}"
  fi

  printf '%s' "$value"
}

get_var_default() {
  local var_name="$1"
  local default_value="$2"
  local value
  value="$(get_var "$var_name")"
  if [[ -z "$value" ]]; then
    value="$default_value"
  fi
  printf '%s' "$value"
}

api_base_url="$(get_var 'API_BASE_URL')"
api_domain="$(get_var 'API_DOMAIN')"

if [[ -z "$api_base_url" ]]; then
  api_base_url="$api_domain"
fi

# Set environment variables from LOCAL_ prefixed variables, falling back to shared values.
export ENVIRONMENT="$(get_var_default 'ENVIRONMENT' 'local')"
export LOG_LEVEL="$(get_var_default 'LOG_LEVEL' 'DEBUG')"
export FRONTEND_URL="$(get_var_default 'FRONTEND_URL' "http://localhost:${LOCAL_SPA_PORT:-5173}")"
export API_DOMAIN="$api_domain"
export API_BASE_URL="$api_base_url"
export VITE_API_BASE_URL="$api_base_url"
export SPA_PORT="$(get_var_default 'SPA_PORT' "${LOCAL_SPA_PORT:-5173}")"
export WIDGET_CDN_DOMAIN="$(get_var 'WIDGET_CDN_DOMAIN')"
export DOWNLOADS_ARTIFACTS_BUCKET="$(get_var_default 'DOWNLOADS_ARTIFACTS_BUCKET' 'innomightlabs-artifacts')"
export DOWNLOADS_ARTIFACTS_REGION="$(get_var_default 'DOWNLOADS_ARTIFACTS_REGION' 'us-east-1')"
export DOWNLOADS_MANIFEST_KEY="$(get_var_default 'DOWNLOADS_MANIFEST_KEY' 'artifacts/plugins/manifest.json')"
export DOWNLOADS_PRESIGN_TTL_SECONDS="$(get_var_default 'DOWNLOADS_PRESIGN_TTL_SECONDS' '900')"
export GOOGLE_CLIENT_ID="$(get_var 'GOOGLE_CLIENT_ID')"
export GOOGLE_CLIENT_SECRET="$(get_var 'GOOGLE_CLIENT_SECRET')"
export JWT_SECRET="$(get_var 'JWT_SECRET')"
export COGNITO_DOMAIN_PREFIX="$(get_var 'COGNITO_DOMAIN_PREFIX')"
export COGNITO_DOMAIN="$(get_var_default 'COGNITO_DOMAIN' "$(get_var 'COGNITO_DOMAIN_URL')")"
export COGNITO_CLIENT_ID="$(get_var 'COGNITO_CLIENT_ID')"
export COGNITO_CLIENT_SECRET="$(get_var 'COGNITO_CLIENT_SECRET')"
export COGNITO_CALLBACK_URLS="$(get_var 'COGNITO_CALLBACK_URLS')"
export COGNITO_LOGOUT_URLS="$(get_var 'COGNITO_LOGOUT_URLS')"
export COGNITO_REDIRECT_URI="$(get_var_default 'COGNITO_REDIRECT_URI' "${api_base_url}/auth/callback/cognito")"
export OPENAI_OAUTH_CLIENT_ID="$(get_var 'OPENAI_OAUTH_CLIENT_ID')"
export OPENAI_OAUTH_SCOPES="$(get_var 'OPENAI_OAUTH_SCOPES')"
export OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS="$(get_var 'OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS')"
export OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW="$(get_var 'OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW')"
export OPENAI_OAUTH_ORIGINATOR="$(get_var 'OPENAI_OAUTH_ORIGINATOR')"
export OPENAI_OAUTH_REDIRECT_URI="$(get_var_default 'OPENAI_OAUTH_REDIRECT_URI' "${api_base_url}/auth/openai")"
export OPENAI_OAUTH_RESPONSES_URL="$(get_var_default 'OPENAI_OAUTH_RESPONSES_URL' 'https://chatgpt.com/backend-api/codex/responses')"
export OPENAI_MODELS="$(get_var 'OPENAI_MODELS')"
export OPENAI_IMAGE_GENERATION_MODELS="$(get_var 'OPENAI_IMAGE_GENERATION_MODELS')"
export SUPERUSER_EMAILS="$(get_var 'SUPERUSER_EMAILS')"
export STRIPE_SECRET_KEY="$(get_var 'STRIPE_SECRET_KEY')"
export STRIPE_PUBLISHABLE_KEY="$(get_var 'STRIPE_PUBLISHABLE_KEY')"
export STRIPE_WEBHOOK_SECRET="$(get_var 'STRIPE_WEBHOOK_SECRET')"
export SES_DOMAIN="$(get_var 'SES_DOMAIN')"
export SES_FROM_EMAIL="$(get_var 'SES_FROM_EMAIL')"
export SES_REPLY_TO_EMAIL="$(get_var 'SES_REPLY_TO_EMAIL')"
export SES_VERIFICATION_EMAIL="$(get_var 'SES_VERIFICATION_EMAIL')"
export MAILJET_API_KEY="$(get_var 'MAILJET_API_KEY')"
export MAILJET_SECRET_KEY="$(get_var 'MAILJET_SECRET_KEY')"
export GITHUB_TOKEN="$(get_var 'GITHUB_TOKEN')"

# Also export common variables used by the local API.
export AWS_REGION_NAME="$(get_var_default 'AWS_REGION_NAME' "${DEV_AWS_REGION_NAME:-eu-west-2}")"
export AWS_DEFAULT_REGION="$AWS_REGION_NAME"
export AWS_REGION="$AWS_REGION_NAME"
export AWS_PROFILE="$(get_var 'AWS_PROFILE')"
export DYNAMODB_ENDPOINT="$(get_var_default 'DYNAMODB_ENDPOINT' 'http://localhost:8001')"
export DYNAMODB_TABLE="${LOCAL_DYNAMODB_TABLE:-dynamic-agent-builder-local}"
export ANTHROPIC_API_KEY="$(get_var 'ANTHROPIC_API_KEY')"
export PINECONE_API_KEY="$(get_var 'PINECONE_API_KEY')"
export PINECONE_HOST="$(get_var 'PINECONE_HOST')"
export PINECONE_INDEX="$(get_var 'PINECONE_INDEX')"
export PRICING_CONFIG_PATH="$(get_var_default 'PRICING_CONFIG_PATH' './api/src/payments/pricing_config.json')"
export STRIPE_CURRENCY="$(get_var_default 'STRIPE_CURRENCY' 'usd')"
export STRIPE_PRICE_STARTER_MONTHLY="$(get_var 'STRIPE_PRICE_STARTER_MONTHLY')"
export STRIPE_PRICE_STARTER_ANNUAL="$(get_var 'STRIPE_PRICE_STARTER_ANNUAL')"
export STRIPE_PRICE_PRO_MONTHLY="$(get_var 'STRIPE_PRICE_PRO_MONTHLY')"
export STRIPE_PRICE_PRO_ANNUAL="$(get_var 'STRIPE_PRICE_PRO_ANNUAL')"
export SKILLS_STORE_BACKEND="$(get_var_default 'SKILLS_STORE_BACKEND' 'local')"
export SKILLS_BUCKET_NAME="$(get_var_default 'SKILLS_BUCKET_NAME' './docs')"

echo "✅ Environment variables set for LOCAL development"
echo ""
echo "Key variables:"
echo "  ENVIRONMENT: $ENVIRONMENT"
echo "  FRONTEND_URL: $FRONTEND_URL"
echo "  API_DOMAIN: $API_DOMAIN"
echo "  AWS_REGION: $AWS_REGION"
echo "  DOWNLOADS_ARTIFACTS_BUCKET: $DOWNLOADS_ARTIFACTS_BUCKET"
echo "  DOWNLOADS_ARTIFACTS_REGION: $DOWNLOADS_ARTIFACTS_REGION"
echo ""
echo "You can now run: cd api && uv run uvicorn main:app --reload"
