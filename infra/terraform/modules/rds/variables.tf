variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "aws_region" {
  type        = string
  description = "AWS region."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID to deploy RDS into."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for the RDS subnet group."
}

variable "rds_security_group_id" {
  type        = string
  description = "Security group ID that allows the EC2 application host to connect to RDS."
}

variable "db_name" {
  type        = string
  description = "PostgreSQL database name."
  default     = "tax_agent"
}

variable "db_username" {
  type        = string
  description = "PostgreSQL master username."
  sensitive   = true
}

variable "db_password" {
  type        = string
  description = "PostgreSQL master password. Use Secrets Manager in production."
  sensitive   = true
}

variable "instance_class" {
  type        = string
  description = <<-EOT
    RDS instance class.

    COST WARNING:
      db.t3.micro  — ~$15/month  (eligible for free tier in some accounts)
      db.t3.small  — ~$30/month
      db.t3.medium — ~$60/month

    Always verify current pricing at https://aws.amazon.com/rds/postgresql/pricing/
    Free tier eligibility: 750 hours/month of db.t3.micro, 20GB storage — check current terms.
  EOT
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage in GB. Free tier includes 20GB."
  default     = 20
}

variable "multi_az" {
  type        = bool
  description = <<-EOT
    Enable Multi-AZ deployment for high availability.

    COST WARNING: Multi-AZ doubles the instance cost.
    Keep false in development.
  EOT
  default     = false
}

variable "deletion_protection" {
  type        = bool
  description = "Prevent accidental deletion. Set true for production."
  default     = false
}

variable "skip_final_snapshot" {
  type        = bool
  description = "Skip final snapshot on deletion. Set false for production."
  default     = true
}

variable "backup_retention_days" {
  type        = number
  description = "Number of days to retain automated backups. 0 = disabled."
  default     = 7
}
