#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "=========================================="
echo "Deploying to UAT environment"
echo "=========================================="
echo ""

# Generate terraform.tfvars for uat environment
echo "📝 Generating terraform.tfvars for UAT..."
"$SCRIPT_DIR/generate_tfvars.sh" uat

# Change to terraform directory
cd "$TERRAFORM_DIR"

# Initialize terraform if needed
if [[ ! -d ".terraform" ]]; then
  echo ""
  echo "🔧 Initializing Terraform..."
  terraform init
fi

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
  echo "✅ Deployment to UAT completed successfully!"
else
  echo ""
  echo "❌ Deployment cancelled."
  rm -f tfplan
  exit 1
fi
