# =============================================================================
# Skills Storage - S3 bucket for tenant-uploaded skill packages (zip) and assets
# =============================================================================

# NOTE: S3 bucket names are globally unique. The default below is "innomightlabs"
# per product requirement, but you can override via var.skills_bucket_name if needed.

resource "aws_s3_bucket" "skills" {
  bucket = var.skills_bucket_name

  tags = {
    Name        = "${var.project_name}-skills"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "skills" {
  bucket = aws_s3_bucket.skills.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "skills" {
  bucket = aws_s3_bucket.skills.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "skills" {
  bucket = aws_s3_bucket.skills.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "skills" {
  bucket = aws_s3_bucket.skills.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}
