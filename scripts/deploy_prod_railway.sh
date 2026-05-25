#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$PROJECT_ROOT/api"

RAILWAY_SERVICE="${RAILWAY_SERVICE:-InnomightLabs API}"
RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"

echo "=========================================="
echo "DEPLOYING API TO RAILWAY PRODUCTION"
echo "=========================================="
echo ""

command -v railway >/dev/null 2>&1 || {
  echo "Error: railway CLI is not installed or not on PATH" >&2
  exit 1
}

echo "Checking Railway project link..."
railway status >/dev/null

echo ""
echo "Generating terraform.tfvars for PROD..."
"$SCRIPT_DIR/generate_tfvars.sh" prod

if [[ -f "$PROJECT_ROOT/.envrc" ]]; then
  SKIP_DEFAULT_ENV=1 source "$PROJECT_ROOT/.envrc"
else
  echo "Error: .envrc file not found at $PROJECT_ROOT/.envrc" >&2
  exit 1
fi

get_var() {
  local var_name="$1"
  local env_var="PROD_${var_name}"
  local value="${!env_var:-}"

  if [[ -z "$value" ]]; then
    value="${!var_name:-}"
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

set_railway_var() {
  local key="$1"
  local value="$2"

  if [[ -z "$value" ]]; then
    return
  fi

  RAILWAY_VAR_ARGS+=("$key=$value")
}

project_name="$(get_var_default 'PROJECT_NAME' 'dynamic-agent-builder')"
aws_region="$(get_var_default 'AWS_REGION_NAME' "$(get_var_default 'AWS_REGION' 'us-east-1')")"
environment_name="$(get_var_default 'ENVIRONMENT' 'prod')"
api_domain="$(get_var 'API_DOMAIN')"
api_base_url="$(get_var 'API_BASE_URL')"
cognito_domain="$(get_var 'COGNITO_DOMAIN')"

if [[ -z "$api_base_url" && -n "$api_domain" ]]; then
  api_base_url="https://$api_domain"
fi

if [[ -z "$cognito_domain" ]]; then
  cognito_domain="$(get_var 'COGNITO_DOMAIN_URL')"
fi

if [[ -z "$api_base_url" ]]; then
  echo "Warning: API_BASE_URL/API_DOMAIN is not set. OAuth callback URLs may default incorrectly." >&2
fi

url_for() {
  local path="$1"
  if [[ -z "$api_base_url" ]]; then
    printf ''
    return
  fi
  printf '%s%s' "$api_base_url" "$path"
}

echo ""
echo "Syncing Railway variables for service '$RAILWAY_SERVICE' in environment '$RAILWAY_ENVIRONMENT'..."

RAILWAY_VAR_ARGS=()

set_railway_var "RAILWAY_DOCKERFILE_PATH" "Dockerfile.railway"
set_railway_var "RAILWAY_HEALTHCHECK_TIMEOUT_SEC" "999"
set_railway_var "ENVIRONMENT" "$environment_name"
set_railway_var "DYNAMODB_TABLE" "$(get_var_default 'DYNAMODB_TABLE' "${project_name}-main")"
set_railway_var "AWS_REGION_NAME" "$aws_region"
set_railway_var "AWS_DEFAULT_REGION" "$aws_region"
set_railway_var "FRONTEND_URL" "$(get_var 'FRONTEND_URL')"
set_railway_var "API_BASE_URL" "$api_base_url"
set_railway_var "JWT_SECRET" "$(get_var 'JWT_SECRET')"
set_railway_var "LOG_LEVEL" "$(get_var_default 'LOG_LEVEL' 'INFO')"

set_railway_var "AWS_ACCESS_KEY_ID" "$(get_var 'AWS_ACCESS_KEY_ID')"
set_railway_var "AWS_SECRET_ACCESS_KEY" "$(get_var 'AWS_SECRET_ACCESS_KEY')"
set_railway_var "AWS_SESSION_TOKEN" "$(get_var 'AWS_SESSION_TOKEN')"

set_railway_var "GOOGLE_CLIENT_ID" "$(get_var 'GOOGLE_CLIENT_ID')"
set_railway_var "GOOGLE_CLIENT_SECRET" "$(get_var 'GOOGLE_CLIENT_SECRET')"
set_railway_var "GOOGLE_DRIVE_REDIRECT_URI" "$(get_var_default 'GOOGLE_DRIVE_REDIRECT_URI' "$(url_for '/auth/google-drive/callback')")"
set_railway_var "GOOGLE_DRIVE_OAUTH_SCOPES" "$(get_var_default 'GOOGLE_DRIVE_OAUTH_SCOPES' 'https://www.googleapis.com/auth/drive')"
set_railway_var "GOOGLE_MAIL_REDIRECT_URI" "$(get_var_default 'GOOGLE_MAIL_REDIRECT_URI' "$(url_for '/auth/google-mail/callback')")"
set_railway_var "GOOGLE_MAIL_OAUTH_SCOPES" "$(get_var_default 'GOOGLE_MAIL_OAUTH_SCOPES' 'https://www.googleapis.com/auth/gmail.modify')"

set_railway_var "OPENAI_OAUTH_CLIENT_ID" "$(get_var 'OPENAI_OAUTH_CLIENT_ID')"
set_railway_var "OPENAI_OAUTH_SCOPES" "$(get_var 'OPENAI_OAUTH_SCOPES')"
set_railway_var "OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS" "$(get_var 'OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS')"
set_railway_var "OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW" "$(get_var 'OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW')"
set_railway_var "OPENAI_OAUTH_ORIGINATOR" "$(get_var 'OPENAI_OAUTH_ORIGINATOR')"
set_railway_var "OPENAI_OAUTH_REDIRECT_URI" "$(get_var_default 'OPENAI_OAUTH_REDIRECT_URI' "$(url_for '/auth/openai')")"
set_railway_var "OPENAI_OAUTH_RESPONSES_URL" "$(get_var 'OPENAI_OAUTH_RESPONSES_URL')"
set_railway_var "OPENAI_MODELS" "$(get_var 'OPENAI_MODELS')"
set_railway_var "OPENAI_IMAGE_GENERATION_BACKEND" "$(get_var_default 'OPENAI_IMAGE_GENERATION_BACKEND' 'codex_oauth')"
set_railway_var "OPENAI_IMAGE_GENERATION_MODELS" "$(get_var 'OPENAI_IMAGE_GENERATION_MODELS')"
set_railway_var "SUPERUSER_EMAILS" "$(get_var 'SUPERUSER_EMAILS')"

set_railway_var "PINECONE_API_KEY" "$(get_var 'PINECONE_API_KEY')"
set_railway_var "PINECONE_HOST" "$(get_var 'PINECONE_HOST')"
set_railway_var "PINECONE_INDEX" "$(get_var 'PINECONE_INDEX')"
set_railway_var "BEDROCK_EMBEDDING_MODEL" "$(get_var_default 'BEDROCK_EMBEDDING_MODEL' 'amazon.titan-embed-text-v2:0')"
set_railway_var "BEDROCK_EMBEDDING_DIMENSION" "$(get_var_default 'BEDROCK_EMBEDDING_DIMENSION' '1024')"

set_railway_var "STRIPE_SECRET_KEY" "$(get_var 'STRIPE_SECRET_KEY')"
set_railway_var "STRIPE_PUBLISHABLE_KEY" "$(get_var 'STRIPE_PUBLISHABLE_KEY')"
set_railway_var "STRIPE_WEBHOOK_SECRET" "$(get_var 'STRIPE_WEBHOOK_SECRET')"

set_railway_var "COGNITO_DOMAIN" "$cognito_domain"
set_railway_var "COGNITO_CLIENT_ID" "$(get_var 'COGNITO_CLIENT_ID')"
set_railway_var "COGNITO_CLIENT_SECRET" "$(get_var 'COGNITO_CLIENT_SECRET')"
set_railway_var "COGNITO_REDIRECT_URI" "$(get_var_default 'COGNITO_REDIRECT_URI' "$(url_for '/auth/callback/cognito')")"

set_railway_var "SES_FROM_EMAIL" "$(get_var 'SES_FROM_EMAIL')"
set_railway_var "SES_REPLY_TO_EMAIL" "$(get_var 'SES_REPLY_TO_EMAIL')"
set_railway_var "MAILJET_API_KEY" "$(get_var 'MAILJET_API_KEY')"
set_railway_var "MAILJET_SECRET_KEY" "$(get_var 'MAILJET_SECRET_KEY')"
set_railway_var "GITHUB_TOKEN" "$(get_var 'GITHUB_TOKEN')"

set_railway_var "DOWNLOADS_ARTIFACTS_BUCKET" "$(get_var_default 'DOWNLOADS_ARTIFACTS_BUCKET' 'innomightlabs-artifacts')"
set_railway_var "DOWNLOADS_ARTIFACTS_REGION" "$(get_var_default 'DOWNLOADS_ARTIFACTS_REGION' 'us-east-1')"
set_railway_var "DOWNLOADS_MANIFEST_KEY" "$(get_var_default 'DOWNLOADS_MANIFEST_KEY' 'artifacts/plugins/manifest.json')"
set_railway_var "DOWNLOADS_PRESIGN_TTL_SECONDS" "$(get_var_default 'DOWNLOADS_PRESIGN_TTL_SECONDS' '900')"
set_railway_var "CONVERSATION_MEDIA_BUCKET" "$(get_var_default 'CONVERSATION_MEDIA_BUCKET' 'innomightlabs-conversations-meta')"
set_railway_var "CONVERSATION_MEDIA_PRESIGN_TTL_SECONDS" "$(get_var_default 'CONVERSATION_MEDIA_PRESIGN_TTL_SECONDS' '900')"

set_railway_var "ASYNC_JOB_BACKEND" "$(get_var_default 'ASYNC_JOB_BACKEND' 'local')"
set_railway_var "ASYNC_JOB_LAMBDA_NAME" "$(get_var 'ASYNC_JOB_LAMBDA_NAME')"
set_railway_var "ACCOUNT_DELETION_LAMBDA_NAME" "$(get_var 'ACCOUNT_DELETION_LAMBDA_NAME')"

if [[ ${#RAILWAY_VAR_ARGS[@]} -gt 0 ]]; then
  railway variable set \
    --service "$RAILWAY_SERVICE" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --skip-deploys \
    "${RAILWAY_VAR_ARGS[@]}" >/dev/null
fi

echo "Railway variables synced."
echo ""
echo "=========================================="
echo "WARNING: You are about to deploy the API to Railway PRODUCTION."
echo "Service: $RAILWAY_SERVICE"
echo "Railway environment: $RAILWAY_ENVIRONMENT"
echo "API_BASE_URL: ${api_base_url:-not set}"
echo "=========================================="
read -r -p "Type 'yes' to deploy to Railway production: "
echo "=========================================="

if [[ "$REPLY" != "yes" ]]; then
  echo ""
  echo "Deployment cancelled."
  exit 1
fi

echo ""
echo "Deploying API to Railway..."
railway up "$API_DIR" \
  --path-as-root \
  --service "$RAILWAY_SERVICE" \
  --environment "$RAILWAY_ENVIRONMENT" \
  --message "prod api deploy from scripts/deploy_prod_railway.sh"

echo ""
echo "Railway deployment command completed."
