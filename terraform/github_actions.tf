resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com"
  ]

  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1"
  ]
}

resource "aws_iam_role" "github_actions_artifact_publisher" {
  name = "${var.project_name}-github-artifact-publisher"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_actions_repository}:ref:refs/heads/prod"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-github-artifact-publisher"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "github_actions_artifact_publisher" {
  name = "${var.project_name}-github-artifact-publisher"
  role = aws_iam_role.github_actions_artifact_publisher.id

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
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/artifacts/plugins/*"
      }
    ]
  })
}
