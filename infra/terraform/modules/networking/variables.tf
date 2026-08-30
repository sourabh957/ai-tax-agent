variable "project" {
  type        = string
  description = "Project name prefix for resource naming."
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, prod)."
}

variable "aws_region" {
  type        = string
  description = "AWS region."
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC."
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for public subnets (one per AZ)."
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for private subnets (one per AZ)."
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones to deploy into."
  default     = []
  # If empty, module uses the first 2 AZs in the region automatically.
}

variable "create_nat_gateway" {
  type        = bool
  description = <<-EOT
    Whether to create a NAT Gateway for private subnet egress.

    COST WARNING: Each NAT Gateway costs ~$35/month plus data transfer fees.
    For development, leave this false and use public subnets for ECS tasks.
    Only enable for production when private subnets are required.
  EOT
  default     = false
}
