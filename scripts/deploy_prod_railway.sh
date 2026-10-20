#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$PROJECT_ROOT/api"
CLI_RUNNER_DIR="$PROJECT_ROOT/infra-cli-runner"
OLLAMA_DIR="$PROJECT_ROOT/ollama-embeddings"

RAILWAY_PROJECT_ID="${RAILWAY_PROJECT_ID:-f71e184d-415c-40ce-886e-b8e293a568ca}"
RAILWAY_SERVICE="${RAILWAY_SERVICE:-InnomightLabs API}"
RAILWAY_CLI_RUNNER_SERVICE="${RAILWAY_CLI_RUNNER_SERVICE:-infra-cli-runner}"
RAILWAY_ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"
DEPLOY_CLI_RUNNER="${DEPLOY_CLI_RUNNER:-true}"
RAILWAY_OLLAMA_SERVICE="${RAILWAY_OLLAMA_SERVICE:-ollama-embeddings}"

echo "=========================================="
echo "DEPLOYING API TO RAILWAY PRODUCTION"
echo "=========================================="
echo ""

command -v railway >/dev/null 2>&1 || {
  echo "Error: railway CLI is not installed or not on PATH" >&2
  exit 1
}

railway_service_exists() {
  local service_name="$1"
  railway service list \
    --project "$RAILWAY_PROJECT_ID" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --json | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$service_name\""
}

require_railway_service() {
  local service_name="$1"
  if railway_service_exists "$service_name"; then
    return
  fi

  echo "Error: service '$service_name' not found in Railway project '$RAILWAY_PROJECT_ID' environment '$RAILWAY_ENVIRONMENT'." >&2
  echo "Available services:" >&2
  railway service list \
    --project "$RAILWAY_PROJECT_ID" \
    --environment "$RAILWAY_ENVIRONMENT"
  exit 1
}

ensure_railway_service() {
  local service_name="$1"
  if railway_service_exists "$service_name"; then
    return
  fi

  echo "Railway service '$service_name' not found. Creating it in project '$RAILWAY_PROJECT_ID' environment '$RAILWAY_ENVIRONMENT'..."
  railway link \
    --project "$RAILWAY_PROJECT_ID" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --json >/dev/null
  railway add \
    --service "$service_name" \
    --json >/dev/null
  echo "Created Railway service '$service_name'."
}

railway_ref() {
  local service_name="$1"
  local variable_name="$2"
  printf '${{%s.%s}}' "$service_name" "$variable_name"
}

# What a service runs: its files (uncommitted edits included) plus the variables set on it. Hashed, so secrets never
# leave this machine. A service whose fingerprint matches the one recorded after its last good deploy is not redeployed.
# FORCE_DEPLOY=true redeploys everything, for what the fingerprint can't see (a base image that moved).
fingerprint() {
  local dir="$1"
  shift
  {
    (cd "$dir" && git ls-files -z --cached --others --exclude-standard | sort -z | xargs -0 shasum -a 256 2>/dev/null) || true
    printf '%s\n' "$@"
  } | shasum -a 256 | cut -d' ' -f1
}

recorded_fingerprint() {
  local service_name="$1"
  railway variable list \
    --project "$RAILWAY_PROJECT_ID" \
    --service "$service_name" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --json 2>/dev/null |
    python3 -c 'import json, sys; print(json.load(sys.stdin).get("DEPLOYED_FINGERPRINT", ""))' 2>/dev/null || true
}

service_changed() {
  local service_name="$1"
  local current="$2"
  [[ "${FORCE_DEPLOY:-false}" == "true" || "$(recorded_fingerprint "$service_name")" != "$current" ]]
}

latest_deployment() {
  railway deployment list \
    --service "$1" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --json --limit 1 2>/dev/null |
    python3 -c 'import json, sys; d = json.load(sys.stdin); print(d[0]["id"], d[0]["status"]) if d else print("", "")' 2>/dev/null || true
}

# Uploads the service, waits for the new deployment to go live, then records its fingerprint. A build or health check
# that fails records nothing, so the next run tries again instead of skipping a broken service.
deploy_service() {
  local service_name="$1"
  local dir="$2"
  local current="$3"
  local message="$4"
  local before id status
  read -r before _ < <(latest_deployment "$service_name") || true

  railway up "$dir" \
    --detach \
    --path-as-root \
    --project "$RAILWAY_PROJECT_ID" \
    --service "$service_name" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --message "$message"

  echo "Waiting for '$service_name' to finish deploying..."
  local deadline=$((SECONDS + 1200))
  while ((SECONDS < deadline)); do
    sleep 10
    read -r id status < <(latest_deployment "$service_name") || true
    if [[ -n "$id" && "$id" != "${before:-}" ]]; then
      case "$status" in
        SUCCESS)
          railway variable set \
            --project "$RAILWAY_PROJECT_ID" \
            --service "$service_name" \
            --environment "$RAILWAY_ENVIRONMENT" \
            --skip-deploys \
            "DEPLOYED_FINGERPRINT=$current" >/dev/null
          echo "'$service_name' is live."
          return 0
          ;;
        FAILED | CRASHED | REMOVED | SKIPPED)
          echo "Error: deployment of '$service_name' ended as $status. Its fingerprint was not recorded." >&2
          return 1
          ;;
      esac
    fi
  done
  echo "Error: '$service_name' was still deploying after 20 minutes. Its fingerprint was not recorded." >&2
  return 1
}

generate_cli_runner_shared_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  python3 -c 'import secrets; print(secrets.token_hex(32))'
}

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

get_prod_var() {
  local var_name="$1"
  local env_var="PROD_${var_name}"
  printf '%s' "${!env_var:-}"
}

get_prod_var_default() {
  local var_name="$1"
  local default_value="$2"
  local value
  value="$(get_prod_var "$var_name")"
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
RAILWAY_CLI_RUNNER_SERVICE="$(get_prod_var_default 'RAILWAY_CLI_RUNNER_SERVICE' "$RAILWAY_CLI_RUNNER_SERVICE")"
api_domain="$(get_var 'API_DOMAIN')"
api_base_url="$(get_var 'API_BASE_URL')"
cognito_domain="$(get_var 'COGNITO_DOMAIN')"
cli_runner_shared_token="$(get_prod_var 'CLI_RUNNER_SHARED_TOKEN')"
cli_runner_max_timeout_seconds="$(get_prod_var_default 'CLI_RUNNER_MAX_TIMEOUT_SECONDS' '120')"
cli_runner_internal_port="$(get_prod_var_default 'CLI_RUNNER_PORT' '8080')"
default_cli_runner_base_url="http://$(railway_ref "$RAILWAY_CLI_RUNNER_SERVICE" 'RAILWAY_PRIVATE_DOMAIN'):$cli_runner_internal_port"
cli_runner_base_url="$(get_prod_var_default 'CLI_RUNNER_BASE_URL' "$default_cli_runner_base_url")"
# Bedrock model invocation is blocked for the AWS account, so prod embeds through the private Ollama
# service. Only PROD_* overrides apply: the shared .envrc values describe the local setup.
embedding_backend="$(get_prod_var_default 'EMBEDDING_BACKEND' 'ollama')"
ollama_embedding_model="$(get_prod_var_default 'OLLAMA_EMBEDDING_MODEL' 'qwen3-embedding:0.6b')"
default_ollama_base_url="http://$(railway_ref "$RAILWAY_OLLAMA_SERVICE" 'RAILWAY_PRIVATE_DOMAIN'):11434"
ollama_base_url="$(get_prod_var_default 'OLLAMA_BASE_URL' "$default_ollama_base_url")"
deploy_ollama="false"
if [[ "$embedding_backend" == "ollama" ]]; then
  deploy_ollama="$(get_prod_var_default 'DEPLOY_OLLAMA' 'true')"
fi

if [[ -z "$api_base_url" && -n "$api_domain" ]]; then
  api_base_url="https://$api_domain"
fi

if [[ -z "$cognito_domain" ]]; then
  cognito_domain="$(get_var 'COGNITO_DOMAIN_URL')"
fi

if [[ -z "$api_base_url" ]]; then
  echo "Warning: API_BASE_URL/API_DOMAIN is not set. OAuth callback URLs may default incorrectly." >&2
fi

echo "Checking Railway project/services..."
require_railway_service "$RAILWAY_SERVICE"
if [[ "$DEPLOY_CLI_RUNNER" == "true" ]]; then
  ensure_railway_service "$RAILWAY_CLI_RUNNER_SERVICE"
fi
if [[ "$deploy_ollama" == "true" ]]; then
  ensure_railway_service "$RAILWAY_OLLAMA_SERVICE"
fi

if [[ "$DEPLOY_CLI_RUNNER" == "true" && -z "$cli_runner_shared_token" ]]; then
  cli_runner_shared_token="$(generate_cli_runner_shared_token)"
  echo "CLI_RUNNER_SHARED_TOKEN was not set. Generated a new production sidecar token for this deployment."
fi

url_for() {
  local path="$1"
  if [[ -z "$api_base_url" ]]; then
    printf ''
    return
  fi
  printf '%s%s' "$api_base_url" "$path"
}

# The API's version: api-v<version> tags count its deploys. VERSION_BUMP=minor|major starts a new minor or
# major (1.1.0, 2.0.0); the default is a patch (1.0.1). The tag is created once railway up has uploaded the build.
APP_VERSION="$(cd "$PROJECT_ROOT" && scripts/next_version.sh api "${VERSION_BUMP:-patch}")"
echo ""
echo "Deploying API version $APP_VERSION"
if [[ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]]; then
  echo "Warning: uncommitted changes. The api-v$APP_VERSION tag will point at HEAD, which lacks them." >&2
fi

echo ""
echo "Syncing Railway variables for service '$RAILWAY_SERVICE' in environment '$RAILWAY_ENVIRONMENT'..."

RAILWAY_VAR_ARGS=()

set_railway_var "RAILWAY_DOCKERFILE_PATH" "Dockerfile.railway"
set_railway_var "RAILWAY_HEALTHCHECK_TIMEOUT_SEC" "999"
set_railway_var "APP_VERSION" "$APP_VERSION"
set_railway_var "ENVIRONMENT" "$environment_name"
set_railway_var "DYNAMODB_TABLE" "$(get_var_default 'DYNAMODB_TABLE' "${project_name}-main")"
set_railway_var "AWS_REGION_NAME" "$aws_region"
set_railway_var "AWS_DEFAULT_REGION" "$aws_region"
set_railway_var "FRONTEND_URL" "$(get_var 'FRONTEND_URL')"
set_railway_var "ACCOUNT_INVITE_EXPIRY_DAYS" "$(get_var_default 'ACCOUNT_INVITE_EXPIRY_DAYS' '7')"
set_railway_var "ACCOUNT_INVITE_PENDING_LIMIT" "$(get_var_default 'ACCOUNT_INVITE_PENDING_LIMIT' '50')"
set_railway_var "ACCOUNT_INVITE_RATE_LIMIT" "$(get_var_default 'ACCOUNT_INVITE_RATE_LIMIT' '20')"
set_railway_var "ACCOUNT_INVITE_RATE_WINDOW_SECONDS" "$(get_var_default 'ACCOUNT_INVITE_RATE_WINDOW_SECONDS' '3600')"
set_railway_var "INVITATION_PREVIEW_RATE_LIMIT" "$(get_var_default 'INVITATION_PREVIEW_RATE_LIMIT' '30')"
set_railway_var "INVITATION_PREVIEW_RATE_WINDOW_SECONDS" "$(get_var_default 'INVITATION_PREVIEW_RATE_WINDOW_SECONDS' '60')"
set_railway_var "AUTH_APP_URLS" "$(get_var 'AUTH_APP_URLS')"
set_railway_var "AUTH_APP_SECRETS" "$(get_var 'AUTH_APP_SECRETS')"
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
set_railway_var "EMBEDDING_BACKEND" "$embedding_backend"
set_railway_var "EMBEDDING_DIMENSION" "$(get_var_default 'EMBEDDING_DIMENSION' '1024')"
set_railway_var "BEDROCK_EMBEDDING_MODEL" "$(get_var_default 'BEDROCK_EMBEDDING_MODEL' 'amazon.titan-embed-text-v2:0')"
set_railway_var "BEDROCK_EMBEDDING_DIMENSION" "$(get_var_default 'BEDROCK_EMBEDDING_DIMENSION' '1024')"
set_railway_var "OLLAMA_BASE_URL" "$ollama_base_url"
set_railway_var "OLLAMA_EMBEDDING_MODEL" "$ollama_embedding_model"
set_railway_var "OLLAMA_TIMEOUT_SECONDS" "$(get_var_default 'OLLAMA_TIMEOUT_SECONDS' '120')"

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

set_railway_var "VISION_MAX_IMAGE_BYTES" "$(get_var_default 'VISION_MAX_IMAGE_BYTES' '5242880')"
set_railway_var "VISION_MAX_IMAGES_PER_MESSAGE" "$(get_var_default 'VISION_MAX_IMAGES_PER_MESSAGE' '4')"
set_railway_var "VISION_MAX_EDGE_PX" "$(get_var_default 'VISION_MAX_EDGE_PX' '2000')"
set_railway_var "VISION_MAX_PIXELS" "$(get_var_default 'VISION_MAX_PIXELS' '40000000')"
set_railway_var "VISION_MAX_CONCURRENCY" "$(get_var_default 'VISION_MAX_CONCURRENCY' '4')"
set_railway_var "VISION_CALL_TIMEOUT_SECONDS" "$(get_var_default 'VISION_CALL_TIMEOUT_SECONDS' '60')"
set_railway_var "VISION_TOOL_TIMEOUT_SECONDS" "$(get_var_default 'VISION_TOOL_TIMEOUT_SECONDS' '120')"
set_railway_var "VISION_PENDING_UPLOAD_TTL_HOURS" "$(get_var_default 'VISION_PENDING_UPLOAD_TTL_HOURS' '24')"
set_railway_var "WIDGET_IMAGE_UPLOADS_PER_VISITOR_HOUR" "$(get_var_default 'WIDGET_IMAGE_UPLOADS_PER_VISITOR_HOUR' '20')"
set_railway_var "WIDGET_IMAGE_UPLOADS_PER_KEY_DAY" "$(get_var_default 'WIDGET_IMAGE_UPLOADS_PER_KEY_DAY' '500')"
set_railway_var "WIDGET_LEAD_FILE_UPLOADS_PER_VISITOR_HOUR" "$(get_var_default 'WIDGET_LEAD_FILE_UPLOADS_PER_VISITOR_HOUR' '10')"
set_railway_var "WIDGET_LEAD_FILE_UPLOADS_PER_KEY_DAY" "$(get_var_default 'WIDGET_LEAD_FILE_UPLOADS_PER_KEY_DAY' '200')"
set_railway_var "API_IMAGE_UPLOADS_PER_KEY_DAY" "$(get_var_default 'API_IMAGE_UPLOADS_PER_KEY_DAY' '1000')"

set_railway_var "ASYNC_JOB_BACKEND" "$(get_var_default 'ASYNC_JOB_BACKEND' 'local')"
set_railway_var "ASYNC_JOB_LAMBDA_NAME" "$(get_var 'ASYNC_JOB_LAMBDA_NAME')"
set_railway_var \
  "CRAWL_JOB_HEARTBEAT_INTERVAL_SECONDS" \
  "$(get_prod_var_default 'CRAWL_JOB_HEARTBEAT_INTERVAL_SECONDS' '60')"
set_railway_var \
  "CRAWL_JOB_STALE_TIMEOUT_SECONDS" \
  "$(get_prod_var_default 'CRAWL_JOB_STALE_TIMEOUT_SECONDS' '900')"
set_railway_var \
  "CRAWL_JOB_REAPER_INTERVAL_SECONDS" \
  "$(get_prod_var_default 'CRAWL_JOB_REAPER_INTERVAL_SECONDS' '300')"
set_railway_var "CRAWLER_BROWSER_FALLBACK" "$(get_prod_var_default 'CRAWLER_BROWSER_FALLBACK' 'true')"
set_railway_var "CRAWLER_BROWSER_TIMEOUT_SECONDS" "$(get_prod_var_default 'CRAWLER_BROWSER_TIMEOUT_SECONDS' '20')"
set_railway_var \
  "BLUEPRINT_APPLY_STALE_TIMEOUT_SECONDS" \
  "$(get_prod_var_default 'BLUEPRINT_APPLY_STALE_TIMEOUT_SECONDS' '900')"
set_railway_var \
  "BLUEPRINT_APPLY_REAPER_INTERVAL_SECONDS" \
  "$(get_prod_var_default 'BLUEPRINT_APPLY_REAPER_INTERVAL_SECONDS' '300')"
set_railway_var \
  "LEAD_EVENT_DISPATCH_INTERVAL_SECONDS" \
  "$(get_prod_var_default 'LEAD_EVENT_DISPATCH_INTERVAL_SECONDS' '5')"
set_railway_var "ACCOUNT_DELETION_LAMBDA_NAME" "$(get_var 'ACCOUNT_DELETION_LAMBDA_NAME')"
set_railway_var "CLI_RUNNER_BASE_URL" "$cli_runner_base_url"
set_railway_var "CLI_RUNNER_SHARED_TOKEN" "$cli_runner_shared_token"
set_railway_var "CLI_RUNNER_TIMEOUT_SECONDS" "$(get_prod_var_default 'CLI_RUNNER_TIMEOUT_SECONDS' '30')"

# The version changes on every run, so it stays out of the fingerprint and is only written when the API deploys.
api_fingerprint_vars=()
for arg in "${RAILWAY_VAR_ARGS[@]}"; do
  [[ "$arg" == APP_VERSION=* ]] || api_fingerprint_vars+=("$arg")
done
api_fingerprint="$(fingerprint "$API_DIR" "${api_fingerprint_vars[@]}")"
deploy_api="false"
if service_changed "$RAILWAY_SERVICE" "$api_fingerprint"; then
  deploy_api="true"
else
  RAILWAY_VAR_ARGS=("${api_fingerprint_vars[@]}")
fi

if [[ ${#RAILWAY_VAR_ARGS[@]} -gt 0 ]]; then
  railway variable set \
    --project "$RAILWAY_PROJECT_ID" \
    --service "$RAILWAY_SERVICE" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --skip-deploys \
    "${RAILWAY_VAR_ARGS[@]}" >/dev/null
fi

echo "Railway variables synced."

if [[ "$DEPLOY_CLI_RUNNER" == "true" ]]; then
  echo ""
  echo "Syncing Railway variables for private sidecar '$RAILWAY_CLI_RUNNER_SERVICE'..."

  RAILWAY_RUNNER_VAR_ARGS=()

  set_runner_railway_var() {
    local key="$1"
    local value="$2"

    if [[ -z "$value" ]]; then
      return
    fi

    RAILWAY_RUNNER_VAR_ARGS+=("$key=$value")
  }

  set_runner_railway_var "RAILWAY_DOCKERFILE_PATH" "Dockerfile.railway"
  set_runner_railway_var "RAILWAY_HEALTHCHECK_TIMEOUT_SEC" "300"
  set_runner_railway_var "PORT" "$cli_runner_internal_port"
  set_runner_railway_var "CLI_RUNNER_SHARED_TOKEN" "$cli_runner_shared_token"
  set_runner_railway_var "CLI_RUNNER_MAX_TIMEOUT_SECONDS" "$cli_runner_max_timeout_seconds"

  cli_runner_fingerprint="$(fingerprint "$CLI_RUNNER_DIR" "${RAILWAY_RUNNER_VAR_ARGS[@]}")"
  deploy_cli_runner="false"
  if service_changed "$RAILWAY_CLI_RUNNER_SERVICE" "$cli_runner_fingerprint"; then
    deploy_cli_runner="true"
  fi

  if [[ ${#RAILWAY_RUNNER_VAR_ARGS[@]} -gt 0 ]]; then
    railway variable set \
      --project "$RAILWAY_PROJECT_ID" \
      --service "$RAILWAY_CLI_RUNNER_SERVICE" \
      --environment "$RAILWAY_ENVIRONMENT" \
      --skip-deploys \
      "${RAILWAY_RUNNER_VAR_ARGS[@]}" >/dev/null
  fi

  echo "Private sidecar variables synced."
fi

ollama_vars=("RAILWAY_DOCKERFILE_PATH=Dockerfile.railway" "RAILWAY_HEALTHCHECK_TIMEOUT_SEC=300")
if [[ "$deploy_ollama" == "true" ]]; then
  ollama_fingerprint="$(fingerprint "$OLLAMA_DIR" "${ollama_vars[@]}")"
  ollama_changed="true"
  service_changed "$RAILWAY_OLLAMA_SERVICE" "$ollama_fingerprint" || ollama_changed="false"
  echo ""
  echo "Syncing Railway variables for private Ollama service '$RAILWAY_OLLAMA_SERVICE'..."
  railway variable set \
    --project "$RAILWAY_PROJECT_ID" \
    --service "$RAILWAY_OLLAMA_SERVICE" \
    --environment "$RAILWAY_ENVIRONMENT" \
    --skip-deploys \
    "${ollama_vars[@]}" >/dev/null
  echo "Ollama service variables synced."
fi
echo ""
echo "=========================================="
echo "WARNING: You are about to deploy to Railway PRODUCTION."
echo "Project ID: $RAILWAY_PROJECT_ID"
echo "API service: $RAILWAY_SERVICE (deploy: $deploy_api)"
echo "CLI runner sidecar: ${RAILWAY_CLI_RUNNER_SERVICE:-not set} (deploy: ${deploy_cli_runner:-false})"
echo "Embedding backend: $embedding_backend (Ollama service: $RAILWAY_OLLAMA_SERVICE, deploy: ${ollama_changed:-false})"
echo "Services whose files and variables match their last good deploy are skipped (FORCE_DEPLOY=true overrides)."
echo "Railway environment: $RAILWAY_ENVIRONMENT"
echo "API_BASE_URL: ${api_base_url:-not set}"
echo "CLI_RUNNER_BASE_URL: ${cli_runner_base_url:-not set}"
echo "=========================================="
read -r -p "Type 'yes' to deploy to Railway production: "
echo "=========================================="

if [[ "$REPLY" != "yes" ]]; then
  echo ""
  echo "Deployment cancelled."
  exit 1
fi

if [[ "${deploy_cli_runner:-false}" == "true" ]]; then
  echo ""
  echo "Deploying private infra CLI runner to Railway..."
  deploy_service "$RAILWAY_CLI_RUNNER_SERVICE" "$CLI_RUNNER_DIR" "$cli_runner_fingerprint" \
    "prod infra cli runner deploy from scripts/deploy_prod_railway.sh"
fi

if [[ "${ollama_changed:-false}" == "true" ]]; then
  echo ""
  echo "Deploying private Ollama embedding service to Railway..."
  deploy_service "$RAILWAY_OLLAMA_SERVICE" "$OLLAMA_DIR" "$ollama_fingerprint" \
    "prod ollama embeddings deploy from scripts/deploy_prod_railway.sh"
fi

if [[ "$deploy_api" == "true" ]]; then
  echo ""
  echo "Deploying API to Railway..."
  deploy_service "$RAILWAY_SERVICE" "$API_DIR" "$api_fingerprint" \
    "prod api $APP_VERSION deploy from scripts/deploy_prod_railway.sh"

  git -C "$PROJECT_ROOT" tag "api-v$APP_VERSION"
  git -C "$PROJECT_ROOT" push origin "api-v$APP_VERSION"
  echo ""
  echo "Railway deployment completed (api $APP_VERSION)."
else
  echo ""
  echo "Railway deployment completed (api unchanged, still on its last version)."
fi
