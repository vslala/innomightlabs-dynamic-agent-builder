#!/bin/bash
set -e

# Configuration
AWS_REGION="eu-west-2"
PROJECT_NAME="dynamic-agent-builder"
ECR_REPO_NAME="${PROJECT_NAME}-api"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo "Deploying to: ${ECR_URI}"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build Docker image
echo "Building Docker image..."
cd "$(dirname "$0")/.."
docker build --platform linux/amd64 -t ${ECR_REPO_NAME}:latest .

# Tag and push
echo "Pushing to ECR..."
docker tag ${ECR_REPO_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest

# Update Lambda function
echo "Updating Lambda function..."
aws lambda update-function-code \
  --function-name ${PROJECT_NAME}-api \
  --image-uri ${ECR_URI}:latest \
  --region ${AWS_REGION}

echo "Deployment complete!"
