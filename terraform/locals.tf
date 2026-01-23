locals {
  api_env_vars = {
    ENVIRONMENT          = var.environment
    DYNAMODB_TABLE       = aws_dynamodb_table.main.name
    AWS_REGION_NAME      = var.aws_region
    FRONTEND_URL         = var.frontend_url
    API_BASE_URL         = var.api_domain != "" ? "https://${var.api_domain}" : aws_apigatewayv2_api.api.api_endpoint
    GOOGLE_CLIENT_ID     = var.google_client_id
    GOOGLE_CLIENT_SECRET = var.google_client_secret
    JWT_SECRET           = var.jwt_secret
    COGNITO_DOMAIN        = "https://${aws_cognito_user_pool_domain.hosted_ui.domain}.auth.${var.aws_region}.amazoncognito.com"
    COGNITO_CLIENT_ID     = aws_cognito_user_pool_client.hosted_ui.id
    COGNITO_CLIENT_SECRET = aws_cognito_user_pool_client.hosted_ui.client_secret
    COGNITO_REDIRECT_URI  = "${var.api_domain != "" ? "https://${var.api_domain}" : aws_apigatewayv2_api.api.api_endpoint}/auth/callback/cognito"
    PINECONE_API_KEY     = var.pinecone_api_key
    PINECONE_HOST        = var.pinecone_host
    PINECONE_INDEX       = var.pinecone_index
    STRIPE_SECRET_KEY            = var.stripe_secret_key
    STRIPE_PUBLISHABLE_KEY       = var.stripe_publishable_key
    STRIPE_WEBHOOK_SECRET        = var.stripe_webhook_secret
    LOG_LEVEL                    = "INFO"
    SES_FROM_EMAIL     = var.ses_from_email
    SES_REPLY_TO_EMAIL = var.ses_reply_to_email
  }

  usage_env_vars = {
    ENVIRONMENT     = var.environment
    DYNAMODB_TABLE  = aws_dynamodb_table.main.name
    AWS_REGION_NAME = var.aws_region
    STRIPE_SECRET_KEY = var.stripe_secret_key
    LOG_LEVEL         = "INFO"
    SES_FROM_EMAIL     = var.ses_from_email
    SES_REPLY_TO_EMAIL = var.ses_reply_to_email
  }
}
