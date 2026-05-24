resource "aws_s3_bucket" "artifacts" {
  bucket = var.downloads_artifacts_bucket

  tags = {
    Name        = var.downloads_artifacts_bucket
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_iam_role_policy" "lambda_artifacts_read" {
  name = "${var.project_name}-lambda-artifacts-read"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.artifacts.arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "artifacts/plugins",
              "artifacts/plugins/*"
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/artifacts/plugins/*"
      }
    ]
  })
}
