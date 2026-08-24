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

# Database (values must be supplied via tfvars — never committed)
variable "db_username" {
  type        = string
  description = "RDS database username"
  default     = ""
  sensitive   = true
}

variable "db_password" {
  type        = string
  description = "RDS database password"
  default     = ""
  sensitive   = true
}
