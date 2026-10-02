# SPA Hosting - S3 + CloudFront for the Engram dashboard SPA
# Only created when spa_domain is set (e.g. dev-engram.innomightlabs.com, engram.innomightlabs.com)

locals {
  spa_enabled = var.spa_domain != "" ? 1 : 0
  spa_api_url = var.api_domain != "" ? "https://${var.api_domain}" : aws_apigatewayv2_api.api.api_endpoint
}

# =============================================================================
# Custom Domain SSL Certificate (ACM) - must be in us-east-1 for CloudFront
# =============================================================================

resource "aws_acm_certificate" "spa" {
  count    = local.spa_enabled
  provider = aws.us_east_1

  domain_name       = var.spa_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "${var.project_name}-spa-cert"
    Environment = var.environment
  }
}

# Certificate validation (requires the DNS record from spa_cert_validation_record to be added in Cloudflare)
resource "aws_acm_certificate_validation" "spa" {
  count    = local.spa_enabled
  provider = aws.us_east_1

  certificate_arn = aws_acm_certificate.spa[0].arn
}

# =============================================================================
# S3 Bucket
# =============================================================================

resource "aws_s3_bucket" "spa" {
  count  = local.spa_enabled
  bucket = "${var.project_name}-spa-bucket"

  tags = {
    Name        = "${var.project_name}-spa"
    Environment = var.environment
  }
}

# Block all public access - CloudFront will access via OAC
resource "aws_s3_bucket_public_access_block" "spa" {
  count  = local.spa_enabled
  bucket = aws_s3_bucket.spa[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "spa" {
  count                             = local.spa_enabled
  name                              = "${var.project_name}-spa-oac"
  description                       = "OAC for SPA hosting"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

# =============================================================================
# CloudFront Distribution
# =============================================================================

resource "aws_cloudfront_distribution" "spa" {
  count               = local.spa_enabled
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.project_name} SPA"
  price_class         = "PriceClass_100" # Use only North America and Europe (cheapest)
  aliases             = [var.spa_domain]

  origin {
    domain_name              = aws_s3_bucket.spa[0].bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.spa[0].id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.spa[0].id
  }

  default_cache_behavior {
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    target_origin_id           = "S3-${aws_s3_bucket.spa[0].id}"
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
    viewer_protocol_policy     = "redirect-to-https"
    compress                   = true
  }

  # Client-side routes (/dashboard/agents/123) have no S3 object. Without ListBucket,
  # S3 answers 403 for missing keys, so both codes fall back to the SPA shell.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.spa[0].certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name        = "${var.project_name}-spa"
    Environment = var.environment
  }
}

# S3 bucket policy to allow CloudFront access
resource "aws_s3_bucket_policy" "spa" {
  count  = local.spa_enabled
  bucket = aws_s3_bucket.spa[0].id

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
        Resource = "${aws_s3_bucket.spa[0].arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.spa[0].arn
          }
        }
      }
    ]
  })
}

# =============================================================================
# Build and upload SPA to S3
# =============================================================================

resource "null_resource" "spa_build_upload" {
  count = local.spa_enabled

  triggers = {
    spa_src_hash = sha256(join("", [
      for file in concat(
        [for file in fileset("${path.module}/../spa/src", "**/*") : "src/${file}"],
        [for file in fileset("${path.module}/../spa/public", "**/*") : "public/${file}"],
        [for file in fileset("${path.module}/../spa/packages/chat-stream-renderer/src", "**/*") : "packages/chat-stream-renderer/src/${file}"],
        ["index.html", "vite.config.ts", "package.json", "yarn.lock"]
      ) : filesha256("${path.module}/../spa/${file}")
    ]))
    api_url   = local.spa_api_url
    bucket_id = aws_s3_bucket.spa[0].id
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../spa"
    command     = <<-EOT
      set -e
      echo "Installing SPA dependencies..."
      yarn install --frozen-lockfile || yarn install

      echo "Building shared chat stream package..."
      ./node_modules/.bin/tsc -p packages/chat-stream-renderer/tsconfig.json

      echo "Building SPA against ${local.spa_api_url}..."
      VITE_API_BASE_URL="${local.spa_api_url}" yarn build

      # Hashed bundles are immutable. No --delete, so tabs still running the
      # previous index.html can lazy-load their old chunks.
      echo "Uploading SPA to S3..."
      aws s3 sync dist/assets/ s3://${aws_s3_bucket.spa[0].id}/assets/ \
        --cache-control "public, max-age=31536000, immutable"

      # Everything else (index.html, favicons) must revalidate so a deploy shows up
      # immediately. CNAME and 404.html only exist for GitHub Pages.
      aws s3 sync dist/ s3://${aws_s3_bucket.spa[0].id}/ \
        --delete \
        --exclude "assets/*" \
        --exclude "CNAME" \
        --exclude "404.html" \
        --cache-control "no-cache"

      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation \
        --distribution-id ${aws_cloudfront_distribution.spa[0].id} \
        --paths "/*"

      echo "SPA deployed successfully!"
    EOT
  }

  depends_on = [
    aws_s3_bucket_policy.spa,
    aws_cloudfront_distribution.spa,
  ]
}
