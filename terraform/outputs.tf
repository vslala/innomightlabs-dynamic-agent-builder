output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.api.repository_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "api_gateway_url" {
  description = "API Gateway HTTP API URL"
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "api_gateway_id" {
  description = "API Gateway HTTP API ID"
  value       = aws_apigatewayv2_api.api.id
}

output "dynamodb_table_name" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.main.name
}

# Widget CDN outputs
output "widget_cdn_domain" {
  description = "CloudFront distribution domain for widget CDN"
  value       = aws_cloudfront_distribution.widget.domain_name
}

output "widget_cdn_distribution_id" {
  description = "CloudFront distribution ID for widget CDN"
  value       = aws_cloudfront_distribution.widget.id
}

output "widget_s3_bucket" {
  description = "S3 bucket name for widget files"
  value       = aws_s3_bucket.widget.id
}

output "widget_embed_url" {
  description = "URL to embed the widget script"
  value       = var.widget_cdn_domain != "" ? "https://${var.widget_cdn_domain}/widget.js" : "https://${aws_cloudfront_distribution.widget.domain_name}/widget.js"
}

output "widget_custom_domain" {
  description = "Custom domain for widget CDN (if configured)"
  value       = var.widget_cdn_domain != "" ? var.widget_cdn_domain : null
}

# Certificate validation DNS record (add this to GoDaddy)
output "widget_cert_validation_record" {
  description = "DNS record to add in GoDaddy for certificate validation"
  value = var.widget_cdn_domain != "" ? {
    name  = tolist(aws_acm_certificate.widget[0].domain_validation_options)[0].resource_record_name
    type  = tolist(aws_acm_certificate.widget[0].domain_validation_options)[0].resource_record_type
    value = tolist(aws_acm_certificate.widget[0].domain_validation_options)[0].resource_record_value
  } : null
}
