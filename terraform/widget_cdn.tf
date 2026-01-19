# Widget CDN - S3 + CloudFront for serving static widget files
# The widget.js file is served from CloudFront for HTTPS and caching

# =============================================================================
# Custom Domain SSL Certificate (ACM) - must be in us-east-1 for CloudFront
# =============================================================================

# Request SSL certificate for custom domain
resource "aws_acm_certificate" "widget" {
  count    = var.widget_cdn_domain != "" ? 1 : 0
  provider = aws.us_east_1

  domain_name       = var.widget_cdn_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "${var.project_name}-widget-cdn-cert"
    Environment = var.environment
  }
}

# Certificate validation (requires DNS record to be added manually in GoDaddy)
resource "aws_acm_certificate_validation" "widget" {
  count    = var.widget_cdn_domain != "" ? 1 : 0
  provider = aws.us_east_1

  certificate_arn = aws_acm_certificate.widget[0].arn

  # Note: DNS validation record must be added manually to GoDaddy
  # The required record will be shown in terraform output
}

# =============================================================================
# S3 Bucket
# =============================================================================

# S3 bucket for widget static files (no versioning to save costs)
resource "aws_s3_bucket" "widget" {
  bucket = "${var.project_name}-widget-cdn"

  tags = {
    Name        = "${var.project_name}-widget-cdn"
    Environment = var.environment
  }
}

# Block all public access - CloudFront will access via OAC
resource "aws_s3_bucket_public_access_block" "widget" {
  bucket = aws_s3_bucket.widget.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CORS configuration for widget files (needed for font files, etc.)
resource "aws_s3_bucket_cors_configuration" "widget" {
  bucket = aws_s3_bucket.widget.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# CloudFront Origin Access Control for S3
resource "aws_cloudfront_origin_access_control" "widget" {
  name                              = "${var.project_name}-widget-oac"
  description                       = "OAC for widget CDN"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "widget" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.project_name} Widget CDN"
  price_class         = "PriceClass_100" # Use only North America and Europe (cheapest)

  # Custom domain (alternate CNAME) - only if configured
  aliases = var.widget_cdn_domain != "" ? [var.widget_cdn_domain] : []

  origin {
    domain_name              = aws_s3_bucket.widget.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.widget.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.widget.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.widget.id}"

    forwarded_values {
      query_string = false
      headers      = ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 86400    # 1 day
    max_ttl                = 31536000 # 1 year
    compress               = true
  }

  # Custom error response for 403/404 (common with S3 OAC)
  custom_error_response {
    error_code         = 403
    response_code      = 404
    response_page_path = "/404.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Use custom certificate if domain is configured, otherwise use default
  dynamic "viewer_certificate" {
    for_each = var.widget_cdn_domain != "" ? [1] : []
    content {
      acm_certificate_arn      = aws_acm_certificate_validation.widget[0].certificate_arn
      ssl_support_method       = "sni-only"
      minimum_protocol_version = "TLSv1.2_2021"
    }
  }

  dynamic "viewer_certificate" {
    for_each = var.widget_cdn_domain == "" ? [1] : []
    content {
      cloudfront_default_certificate = true
    }
  }

  tags = {
    Name        = "${var.project_name}-widget-cdn"
    Environment = var.environment
  }
}

# S3 bucket policy to allow CloudFront access
resource "aws_s3_bucket_policy" "widget" {
  bucket = aws_s3_bucket.widget.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.widget.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.widget.arn
          }
        }
      }
    ]
  })
}

# Build and upload widget to S3
resource "null_resource" "widget_build_upload" {
  # Rebuild when widget source changes
  triggers = {
    # Hash of key widget source files to detect changes
    widget_src_hash = sha256(join("", [
      filesha256("${path.module}/../spa/widget/src/index.ts"),
      filesha256("${path.module}/../spa/widget/package.json"),
      filesha256("${path.module}/../spa/widget/rollup.config.js"),
    ]))
    # Also rebuild if bucket changes
    bucket_id = aws_s3_bucket.widget.id
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../spa/widget"
    command     = <<-EOT
      echo "Installing widget dependencies..."
      yarn install --frozen-lockfile || yarn install

      echo "Building widget..."
      yarn build

      echo "Uploading widget to S3..."
      aws s3 sync dist/ s3://${aws_s3_bucket.widget.id}/ \
        --delete \
        --cache-control "public, max-age=31536000" \
        --exclude "*.html"

      # HTML files with shorter cache
      aws s3 sync dist/ s3://${aws_s3_bucket.widget.id}/ \
        --exclude "*" \
        --include "*.html" \
        --cache-control "public, max-age=3600"

      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation \
        --distribution-id ${aws_cloudfront_distribution.widget.id} \
        --paths "/*"

      echo "Widget deployed successfully!"
    EOT
  }

  depends_on = [
    aws_s3_bucket.widget,
    aws_cloudfront_distribution.widget,
  ]
}
