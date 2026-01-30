#!/usr/bin/env bash
set -euo pipefail

export TF_DATA_DIR=".terraform-dev"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
echo "=========================================="
echo "Deploying to DEV environment"
echo "=========================================="
echo ""

# Generate terraform.tfvars for dev environment
echo "📝 Generating terraform.tfvars for DEV..."
"$SCRIPT_DIR/generate_tfvars.sh" dev

# Change to terraform directory
cd "$TERRAFORM_DIR"

# Initialize terraform (always needed since we are dealing with multiple backends)
echo ""
echo "🔧 Initializing Terraform..."
terraform init --backend-config=backend-eu-west-2.hcl


# Run terraform plan
echo ""
echo "📋 Running terraform plan..."
terraform plan -out=tfplan

# Ask user to continue
echo ""
echo "=========================================="
read -p "Do you want to apply this plan? (yes/no): " -r
echo "=========================================="

if [[ "$REPLY" =~ ^[Yy][Ee][Ss]$ ]]; then
  echo ""
  echo "🚀 Applying terraform changes..."
  terraform apply tfplan

  # Clean up plan file
  rm -f tfplan

  echo ""
  echo "✅ Deployment to DEV completed successfully!"
else
  echo ""
  echo "❌ Deployment cancelled."
  rm -f tfplan
  exit 1
fi
