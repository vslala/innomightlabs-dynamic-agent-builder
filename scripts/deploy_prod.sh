#!/usr/bin/env bash
set -euo pipefail

export TF_DATA_DIR=".terraform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "=========================================="
echo "⚠️  DEPLOYING TO PRODUCTION ENVIRONMENT ⚠️"
echo "=========================================="
echo ""

# Generate terraform.tfvars for prod environment
echo "📝 Generating terraform.tfvars for PROD..."
"$SCRIPT_DIR/generate_tfvars.sh" prod

# Change to terraform directory
cd "$TERRAFORM_DIR"

# Initialize terraform if needed
# Initialize terraform (always needed since we are dealing with multiple backends)
echo ""
echo "🔧 Initializing Terraform..."
terraform init --backend-config=backend-us-east-1.hcl

# Run terraform plan
echo ""
echo "📋 Running terraform plan..."
terraform plan -out=tfplan

# Ask user to continue with extra confirmation for production
echo ""
echo "=========================================="
echo "⚠️  WARNING: You are about to deploy to PRODUCTION!"
echo "=========================================="
read -p "Are you sure you want to apply this plan to PRODUCTION? (type 'yes' to confirm): " -r
echo "=========================================="

if [[ "$REPLY" == "yes" ]]; then
  echo ""
  echo "🚀 Applying terraform changes to PRODUCTION..."
  terraform apply tfplan

  # Clean up plan file
  rm -f tfplan

  echo ""
  echo "✅ Deployment to PRODUCTION completed successfully!"
else
  echo ""
  echo "❌ Deployment cancelled."
  rm -f tfplan
  exit 1
fi
