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
  # Timeout increased to 15 minutes to support async crawl jobs
  # HTTP requests are still bounded by API Gateway's 30 second timeout
  timeout       = 900
  memory_size   = 256

  environment {
    variables = {
      ENVIRONMENT          = var.environment
      DYNAMODB_TABLE       = aws_dynamodb_table.main.name
      AWS_REGION_NAME      = var.aws_region
      FRONTEND_URL         = var.frontend_url
      API_BASE_URL         = aws_apigatewayv2_api.api.api_endpoint
      GOOGLE_CLIENT_ID     = var.google_client_id
      GOOGLE_CLIENT_SECRET = var.google_client_secret
      JWT_SECRET           = var.jwt_secret
      # Cognito Hosted UI
      COGNITO_DOMAIN        = "https://${aws_cognito_user_pool_domain.hosted_ui.domain}.auth.${var.aws_region}.amazoncognito.com"
      COGNITO_CLIENT_ID     = aws_cognito_user_pool_client.hosted_ui.id
      COGNITO_CLIENT_SECRET = aws_cognito_user_pool_client.hosted_ui.client_secret
      COGNITO_REDIRECT_URI = coalesce(
        var.cognito_redirect_uri,
        "${aws_apigatewayv2_api.api.api_endpoint}/auth/callback/cognito"
      )
      # Pinecone Vector Store
      PINECONE_API_KEY     = var.pinecone_api_key
      PINECONE_HOST        = var.pinecone_host
      PINECONE_INDEX       = var.pinecone_index
      # Stripe
      STRIPE_SECRET_KEY            = var.stripe_secret_key
      STRIPE_PUBLISHABLE_KEY       = var.stripe_publishable_key
      STRIPE_WEBHOOK_SECRET        = var.stripe_webhook_secret
      # SES
      SES_FROM_EMAIL     = var.ses_from_email
      SES_REPLY_TO_EMAIL = var.ses_reply_to_email
    }
  }

  tags = {
    Name        = "${var.project_name}-api"
    Environment = var.environment
  }

  depends_on = [
    null_resource.docker_build_push,
    null_resource.stripe_pricing_sync,
  ]

  lifecycle {
    ignore_changes = [image_uri]
  }
}

# Lambda for DynamoDB stream usage updates
resource "aws_lambda_function" "usage_events" {
  function_name = "${var.project_name}-usage-events"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}:latest"
  timeout       = 60
  memory_size   = 256

  environment {
    variables = {
      ENVIRONMENT     = var.environment
      DYNAMODB_TABLE  = aws_dynamodb_table.main.name
      AWS_REGION_NAME = var.aws_region
      STRIPE_SECRET_KEY = var.stripe_secret_key
      SES_FROM_EMAIL     = var.ses_from_email
      SES_REPLY_TO_EMAIL = var.ses_reply_to_email
    }
  }

  image_config {
    command = ["lambdas.usage_stream_handler.handler.handler"]
  }

  tags = {
    Name        = "${var.project_name}-usage-events"
    Environment = var.environment
  }

  depends_on = [
    null_resource.docker_build_push,
    null_resource.stripe_pricing_sync,
  ]

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_event_source_mapping" "usage_events" {
  event_source_arn  = aws_dynamodb_table.main.stream_arn
  function_name     = aws_lambda_function.usage_events.arn
  starting_position = "LATEST"
  batch_size        = 100
}

# Sync Stripe products/prices from pricing config before lambda deploys
resource "null_resource" "stripe_pricing_sync" {
  triggers = {
    pricing_config_hash = filesha256("${path.module}/../api/src/payments/${var.environment}_pricing_config.json")
    stripe_secret_key   = var.stripe_secret_key
    environment         = var.environment
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../api"
    command = <<-EOT
      STRIPE_API_KEY="${var.stripe_secret_key}" \
      STRIPE_CURRENCY="gbp" \
      PRICING_CONFIG_PATH="${path.module}/../api/src/payments/${var.environment}_pricing_config.json" \
      uv run scripts/stripe_pricing_sync.py
    EOT
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

# Lambda self-invoke permission (for async crawl job processing)
resource "aws_iam_role_policy" "lambda_self_invoke" {
  name = "${var.project_name}-lambda-self-invoke"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.api.arn
      }
    ]
  })
}

# SES permissions for Lambda (send emails)
resource "aws_iam_role_policy" "lambda_ses" {
  name = "${var.project_name}-lambda-ses"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}
