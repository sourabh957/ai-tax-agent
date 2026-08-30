variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "project" {
  type        = string
  description = "Project name prefix for resource naming"
  default     = "ai-tax-agent"
}

variable "db_name" {
  type        = string
  description = "PostgreSQL database name"
  default     = "tax_agent"
}

variable "db_username" {
  type      = string
  sensitive = true
  default   = ""
}

variable "db_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy to ECS"
  default     = "latest"
}

variable "ecs_desired_count" {
  type        = number
  description = "Number of ECS tasks. Set to 0 to stop all tasks (zero compute cost)."
  default     = 0
  # Default 0 in dev — increment to 1 when actively testing
}

variable "alarm_email" {
  type        = string
  description = "Email address for CloudWatch alarm notifications. Leave empty to skip."
  default     = ""
}