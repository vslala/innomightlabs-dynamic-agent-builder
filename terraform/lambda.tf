# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-lambda-role"
    Environment = var.environment
  }
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda function
resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}:latest"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      ENVIRONMENT          = var.environment
      DYNAMODB_TABLE       = aws_dynamodb_table.main.name
      AWS_REGION_NAME      = var.aws_region
      FRONTEND_URL         = var.frontend_url
      API_BASE_URL         = var.api_domain != "" ? "https://${var.api_domain}" : aws_apigatewayv2_api.api.api_endpoint
      GOOGLE_CLIENT_ID     = var.google_client_id
      GOOGLE_CLIENT_SECRET = var.google_client_secret
      JWT_SECRET           = var.jwt_secret
      # Pinecone Vector Store
      PINECONE_API_KEY     = var.pinecone_api_key
      PINECONE_HOST        = var.pinecone_host
      PINECONE_INDEX       = var.pinecone_index
    }
  }

  tags = {
    Name        = "${var.project_name}-api"
    Environment = var.environment
  }

  depends_on = [null_resource.docker_build_push]

  lifecycle {
    ignore_changes = [image_uri]
  }
}

# Bedrock permissions for Lambda (required for model listing and embeddings)
resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "${var.project_name}-lambda-bedrock"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:ListFoundationModels",
          "bedrock:GetFoundationModel"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.*"
        ]
      }
    ]
  })
}
