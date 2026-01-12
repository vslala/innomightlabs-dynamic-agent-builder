# Get AWS account ID and region for ECR login
data "aws_caller_identity" "current" {}

# Build and push Docker image to ECR
resource "null_resource" "docker_build_push" {
  triggers = {
    # Rebuild when these files change
    dockerfile_hash = filemd5("${path.module}/../Dockerfile")
    main_hash       = filemd5("${path.module}/../main.py")
    pyproject_hash  = filemd5("${path.module}/../pyproject.toml")
    lock_hash       = filemd5("${path.module}/../uv.lock")
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
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
