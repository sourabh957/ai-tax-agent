variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "prod"
}

variable "project" {
  type        = string
  description = "Project name prefix for resource naming"
  default     = "ai-tax-agent"
}

variable "db_username" {
  type      = string
  default   = ""
  sensitive = true
}

variable "db_password" {
  type      = string
  default   = ""
  sensitive = true
}
