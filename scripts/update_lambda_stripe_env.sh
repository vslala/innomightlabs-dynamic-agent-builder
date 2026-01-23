#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-}"
if [[ -z "$ENVIRONMENT" ]]; then
  echo "Usage: $0 <dev|uat|prod>" >&2
  exit 1
fi

case "$ENVIRONMENT" in
  dev|uat|prod) ;;
  *) echo "Invalid environment: $ENVIRONMENT (use dev, uat, or prod)" >&2; exit 1 ;;
esac

AWS_REGION="${AWS_REGION_NAME:-us-east-1}"
API_FUNCTION="${API_LAMBDA_NAME:-dynamic-agent-builder-api}"
USAGE_FUNCTION="${USAGE_LAMBDA_NAME:-dynamic-agent-builder-usage-events}"

case "$ENVIRONMENT" in
  dev)
    STRIPE_SECRET_KEY="${STRIPE_API_KEY_DEV:-}"
    STRIPE_PUBLISHABLE_KEY="${STRIPE_PUB_KEY_DEV:-}"
    STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET_DEV:-}"
    ;;
  uat)
    STRIPE_SECRET_KEY="${STRIPE_API_KEY_UAT:-}"
    STRIPE_PUBLISHABLE_KEY="${STRIPE_PUB_KEY_UAT:-}"
    STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET_UAT:-}"
    ;;
  prod)
    STRIPE_SECRET_KEY="${STRIPE_API_KEY_PROD:-}"
    STRIPE_PUBLISHABLE_KEY="${STRIPE_PUB_KEY_PROD:-}"
    STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-}"
    ;;
esac

required_vars=(STRIPE_SECRET_KEY STRIPE_PUBLISHABLE_KEY STRIPE_WEBHOOK_SECRET)
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required env var: $var for $ENVIRONMENT" >&2
    exit 1
  fi
done

api_env_file="$(mktemp)"
usage_env_file="$(mktemp)"

cat > "$api_env_file" <<EOF
{
  "FunctionName": "${API_FUNCTION}",
  "Environment": {
    "Variables": {
      "STRIPE_SECRET_KEY": "${STRIPE_SECRET_KEY}",
      "STRIPE_PUBLISHABLE_KEY": "${STRIPE_PUBLISHABLE_KEY}",
      "STRIPE_WEBHOOK_SECRET": "${STRIPE_WEBHOOK_SECRET}"
    }
  }
}
EOF

cat > "$usage_env_file" <<EOF
{
  "FunctionName": "${USAGE_FUNCTION}",
  "Environment": {
    "Variables": {
      "STRIPE_SECRET_KEY": "${STRIPE_SECRET_KEY}"
    }
  }
}
EOF

aws lambda update-function-configuration \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${api_env_file}"

aws lambda update-function-configuration \
  --region "${AWS_REGION}" \
  --cli-input-json "file://${usage_env_file}"

rm -f "$api_env_file" "$usage_env_file"

echo "Updated Stripe env vars for ${API_FUNCTION} and ${USAGE_FUNCTION} in ${AWS_REGION} ($ENVIRONMENT)"
