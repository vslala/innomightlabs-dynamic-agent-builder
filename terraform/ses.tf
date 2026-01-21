resource "aws_ses_domain_identity" "primary" {
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "primary" {
  domain = aws_ses_domain_identity.primary.domain
}

resource "aws_ses_email_identity" "verification" {
  email = var.ses_verification_email
}
