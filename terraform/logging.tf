resource "aws_cloudwatch_log_group" "lambda_api" {
  name              = "/aws/lambda/${var.project_name}-api"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-api"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "lambda_usage_events" {
  name              = "/aws/lambda/${var.project_name}-usage-events"
  retention_in_days = 7

  tags = {
    Name        = "${var.project_name}-usage-events"
    Environment = var.environment
  }
}
