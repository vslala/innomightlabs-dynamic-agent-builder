variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-west-2"
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

variable "jwt_secret" {
  description = "JWT secret for signing tokens"
  type        = string
  sensitive   = true
}

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
