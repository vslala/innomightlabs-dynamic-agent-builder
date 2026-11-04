resource "aws_cognito_user_pool" "main" {
  name                     = "${var.project_name}-user-pool"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }
}

resource "aws_cognito_user_pool_client" "hosted_ui" {
  name                                 = "${var.project_name}-web-client"
  user_pool_id                         = aws_cognito_user_pool.main.id
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls
  supported_identity_providers         = ["COGNITO"]
  prevent_user_existence_errors        = "ENABLED"
}

resource "aws_cognito_user_pool_domain" "hosted_ui" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.main.id
}

# The demo user that Playwright signs in as to record product videos. Its credentials are private to
# the team; it is not a shared trial login. The password is set permanently (no forced change on first
# login) and no invitation email is sent, so the hosted UI form is all a script has to fill in.
resource "aws_cognito_user" "demo" {
  count = var.demo_user_email == "" ? 0 : 1

  user_pool_id   = aws_cognito_user_pool.main.id
  username       = var.demo_user_email
  password       = var.demo_user_password
  message_action = "SUPPRESS"

  attributes = {
    email          = var.demo_user_email
    email_verified = true
  }

  lifecycle {
    precondition {
      condition     = var.demo_user_password != ""
      error_message = "Set DEMO_USER_PASSWORD when DEMO_USER_EMAIL is set."
    }
  }
}
