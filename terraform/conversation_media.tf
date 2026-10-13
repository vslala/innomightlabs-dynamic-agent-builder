resource "aws_s3_bucket" "conversation_media" {
  bucket = var.conversation_media_bucket

  tags = {
    Name        = var.conversation_media_bucket
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "guest_session_archives" {
  bucket = aws_s3_bucket.conversation_media.id

  rule {
    id     = "expire-guest-session-archives"
    status = "Enabled"

    filter {
      tag {
        key   = "retention"
        value = "guest-session"
      }
    }

    expiration {
      days = var.guest_archive_retention_days
    }
  }

  # An uploaded image nobody sent. The API retags it once a message carries it, which takes it out of this rule.
  # S3 can't expire in less than a day, so VISION_PENDING_UPLOAD_TTL_HOURS must stay at or under 24.
  rule {
    id     = "expire-pending-image-uploads"
    status = "Enabled"

    filter {
      tag {
        key   = "retention"
        value = "pending-upload"
      }
    }

    expiration {
      days = 1
    }
  }
}

resource "aws_iam_role_policy" "lambda_conversation_media" {
  name = "${var.project_name}-lambda-conversation-media"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.conversation_media.arn
        Condition = {
          StringLike = {
            "s3:prefix" = ["agents/*"]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:PutObjectTagging",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.conversation_media.arn}/agents/*"
      }
    ]
  })
}
