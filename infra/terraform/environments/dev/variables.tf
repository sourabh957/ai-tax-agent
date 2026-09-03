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

variable "key_name" {
  type        = string
  description = "EC2 key pair name for SSH access. Prefer restricting SSH by CIDR."
  default     = ""
}

variable "domain_name" {
  type        = string
  description = "Public domain routed to the EC2 instance and Nginx reverse proxy."
  default     = ""
}

variable "ssh_allowed_cidr" {
  type        = string
  description = "CIDR allowed to SSH to the EC2 instance. Restrict this in production."
  default     = "0.0.0.0/0"
}

variable "instance_type" {
  type        = string
  description = "EC2 Spot instance type for the application host."
  default     = "t4g.small"
}

variable "alarm_email" {
  type        = string
  description = "Email address for CloudWatch alarm notifications. Leave empty to skip."
  default     = ""
}