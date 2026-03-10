variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "dynamic-agent-builder"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "frontend_url" {
  description = "Frontend URL for OAuth redirects"
  type        = string
  default     = "http://localhost:5173/innomightlabs-dynamic-agent-builder"
}

variable "google_client_id" {
  description = "Google OAuth Client ID"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth Client Secret"
  type        = string
  sensitive   = true
}

variable "openai_oauth_client_id" {
  description = "OpenAI OAuth client ID for PKCE authorization"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_oauth_scopes" {
  description = "OpenAI OAuth scopes"
  type        = string
  default     = "openid profile email offline_access"
}

variable "openai_oauth_id_token_add_organizations" {
  description = "OpenAI OAuth authorize flag: id_token_add_organizations"
  type        = bool
  default     = false
}

variable "openai_oauth_codex_cli_simplified_flow" {
  description = "OpenAI OAuth authorize flag: codex_cli_simplified_flow"
  type        = bool
  default     = false
}

variable "openai_oauth_originator" {
  description = "OpenAI OAuth authorize optional originator value"
  type        = string
  default     = ""
}

variable "openai_oauth_redirect_uri" {
  description = "Optional explicit OpenAI OAuth redirect URI override"
  type        = string
  default     = ""
}

variable "openai_oauth_responses_url" {
  description = "OpenAI OAuth responses endpoint URL (Codex/ChatGPT backend)"
  type        = string
  default     = "https://chatgpt.com/backend-api/codex/responses"
}

variable "openai_models" {
  description = "Comma-separated OpenAI model IDs exposed in the app"
  type        = string
  default     = "gpt-5.4,gpt-5.3-codex,gpt-5.2-codex,gpt-5.2,gpt-5.1-codex-max,gpt-5.1-codex-mini"
}

variable "jwt_secret" {
  description = "JWT secret for signing tokens"
  type        = string
  sensitive   = true
}

variable "widget_cdn_domain" {
  description = "Custom domain for widget CDN (e.g., cdn.innomightlabs.com)"
  type        = string
  default     = ""
}

variable "api_domain" {
  description = "Custom domain for API (e.g., api.innomightlabs.com)"
  type        = string
  default     = ""
}

# Pinecone Vector Store
variable "pinecone_api_key" {
  description = "Pinecone API key for vector storage"
  type        = string
  sensitive   = true
}

variable "pinecone_host" {
  description = "Pinecone index host URL"
  type        = string
}

variable "pinecone_index" {
  description = "Pinecone index name"
  type        = string
  default     = "innomightlabs-knowledge"
}

variable "cognito_domain_prefix" {
  description = "Cognito Hosted UI domain prefix (e.g., innomightlabs-auth)"
  type        = string
  default     = "innomightlabs-auth"
}

variable "cognito_redirect_uri" {
  description = "Redirect after login url"
  type        = string
  default     = "https://api.innomight.com/auth/callback/cognito"
}

variable "cognito_callback_urls" {
  description = "Allowed callback URLs for Cognito Hosted UI"
  type        = list(string)
  default     = ["http://localhost:8000/auth/callback/cognito"]
}

variable "cognito_logout_urls" {
  description = "Allowed logout URLs for Cognito Hosted UI"
  type        = list(string)
  default     = ["http://localhost:5173/"]
}

# Stripe
variable "stripe_secret_key" {
  description = "Stripe secret key"
  type        = string
  sensitive   = true
}

variable "stripe_publishable_key" {
  description = "Stripe publishable key"
  type        = string
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret"
  type        = string
  sensitive   = true
}

# SES
variable "ses_domain" {
  description = "SES domain identity (e.g., innomightlabs.com)"
  type        = string
  default     = "innomightlabs.com"
}

variable "ses_from_email" {
  description = "From email address for SES (e.g., noreply@innomightlabs.com)"
  type        = string
  default     = "noreply@innomightlabs.com"
}

variable "ses_reply_to_email" {
  description = "Reply-to email address for SES (optional)"
  type        = string
  default     = ""
}

variable "ses_verification_email" {
  description = "Email identity to verify for SES sandbox/testing"
  type        = string
  default     = ""
}

# Mailjet
variable "mailjet_api_key" {
  description = "Mailjet API key for email delivery"
  type        = string
  sensitive   = true
  default     = ""
}

variable "mailjet_secret_key" {
  description = "Mailjet secret key for email delivery"
  type        = string
  sensitive   = true
  default     = ""
}
