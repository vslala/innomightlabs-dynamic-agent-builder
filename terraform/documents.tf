# Uploaded documents (knowledge bases, conversations): the original and every parsed output, one prefix per document
# under {account_id}/{owner_kind}/{owner_id}/{document_id}/. Payslips and statements live here, so it is private,
# encrypted and unversioned: a delete is final. See docs/LLD-documents.md.
#
# Every document-related prefix lives in this bucket. Only the Railway API reads and writes it, with the access keys of
# an IAM user that is not managed here: that user needs s3:ListBucket on the bucket and s3:GetObject, s3:PutObject and
# s3:DeleteObject on its objects. No Lambda touches it (document work runs in the Railway process).
resource "aws_s3_bucket" "documents" {
  bucket = var.documents_bucket

  tags = {
    Name        = var.documents_bucket
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Disabled"
  }
}
