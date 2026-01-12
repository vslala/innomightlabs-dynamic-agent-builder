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
