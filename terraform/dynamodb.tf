# DynamoDB single table design
# pk = partition key (e.g., User#{email})
# sk = sort key (e.g., User#Metadata, User#Agent#{agent_id})
resource "aws_dynamodb_table" "main" {
  name         = "${var.project_name}-main"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI2 attributes for API key lookups and visitor lookups
  attribute {
    name = "gsi2_pk"
    type = "S"
  }

  attribute {
    name = "gsi2_sk"
    type = "S"
  }

  # GSI2: Used for API key lookup by public_key and visitor lookup
  # Pattern: gsi2_pk=ApiKey#{public_key}, gsi2_sk=Agent#{agent_id}
  # Pattern: gsi2_pk=Visitor#{visitor_id}, gsi2_sk=Agent#{agent_id}
  global_secondary_index {
    name            = "gsi2"
    hash_key        = "gsi2_pk"
    range_key       = "gsi2_sk"
    projection_type = "ALL"
  }

  tags = {
    Name        = "${var.project_name}-main"
    Environment = var.environment
  }
}

# Add DynamoDB permissions to Lambda role
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.project_name}-lambda-dynamodb"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams"
        ]
        Resource = [
          aws_dynamodb_table.main.arn,
          "${aws_dynamodb_table.main.arn}/index/*",
          aws_dynamodb_table.main.stream_arn
        ]
      }
    ]
  })
}
