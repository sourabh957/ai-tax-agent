variable "vpc_id" {
  type        = string
  description = "VPC ID where the security groups will be created."
}

variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "ssh_allowed_cidr" {
  type        = string
  description = "CIDR allowed to SSH to the EC2 instance. Restrict this in production."
  default     = "0.0.0.0/0"
}
