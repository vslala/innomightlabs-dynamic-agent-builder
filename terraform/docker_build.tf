# Get AWS account ID and region for ECR login
data "aws_caller_identity" "current" {}

# Path to API directory (terraform is now at root level)
locals {
  api_dir       = "${path.module}/../api"
  src_files     = fileset("${local.api_dir}/src", "**/*.py")
  src_hash      = md5(join("", [for f in local.src_files : filemd5("${local.api_dir}/src/${f}")]))
  lambdas_files = fileset("${local.api_dir}/lambdas", "**/*.py")
  lambdas_hash  = md5(join("", [for f in local.lambdas_files : filemd5("${local.api_dir}/lambdas/${f}")]))
}

# Build and push Docker image to ECR
resource "null_resource" "docker_build_push" {
  triggers = {
    # Rebuild when these files change
    dockerfile_hash = filemd5("${local.api_dir}/Dockerfile")
    main_hash       = filemd5("${local.api_dir}/main.py")
    pyproject_hash  = filemd5("${local.api_dir}/pyproject.toml")
    lock_hash       = filemd5("${local.api_dir}/uv.lock")
    src_hash        = local.src_hash
    lambdas_hash    = local.lambdas_hash
  }

  provisioner "local-exec" {
    working_dir = local.api_dir
    command     = <<-EOT
      set -e

      AWS_ACCOUNT_ID="${data.aws_caller_identity.current.account_id}"
      AWS_REGION="${var.aws_region}"
      ECR_URI="${aws_ecr_repository.api.repository_url}"

      echo "Logging in to ECR..."
      aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

      echo "Building Docker image..."
      docker build --platform linux/amd64 -t ${var.project_name}-api:latest .

      echo "Tagging and pushing to ECR..."
      docker tag ${var.project_name}-api:latest $ECR_URI:latest
      docker push $ECR_URI:latest

      echo "Docker image pushed successfully!"
    EOT
  }

  depends_on = [aws_ecr_repository.api]
}

# Update Lambda function with the new image after Docker push
resource "null_resource" "lambda_update" {
  triggers = {
    # Update Lambda whenever docker_build_push is triggered
    docker_build_id = null_resource.docker_build_push.id
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      echo "Updating API Lambda function with new image..."
      aws lambda update-function-code \
        --function-name ${var.project_name}-api \
        --image-uri ${aws_ecr_repository.api.repository_url}:latest \
        --region ${var.aws_region}

      echo "Updating usage_events Lambda function with new image..."
      aws lambda update-function-code \
        --function-name ${var.project_name}-usage-events \
        --image-uri ${aws_ecr_repository.api.repository_url}:latest \
        --region ${var.aws_region}

      echo "Waiting for API Lambda update to complete..."
      aws lambda wait function-updated \
        --function-name ${var.project_name}-api \
        --region ${var.aws_region}

      echo "Waiting for usage_events Lambda update to complete..."
      aws lambda wait function-updated \
        --function-name ${var.project_name}-usage-events \
        --region ${var.aws_region}

      echo "Both Lambda functions updated successfully!"
    EOT
  }

  depends_on = [
    null_resource.docker_build_push,
    aws_lambda_function.api,
    aws_lambda_function.usage_events
  ]
}
