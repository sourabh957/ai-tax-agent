variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "log_retention_days" {
  type        = number
  description = <<-EOT
    CloudWatch log retention in days.

    COST: CloudWatch Logs storage is ~$0.03/GB/month.
    Shorter retention = lower cost.
    Recommended: 7-14 days in dev, 30-90 days in production.
  EOT
  default     = 14
}

variable "ecs_cluster_name" {
  type        = string
  description = "ECS cluster name (used for CPU/memory metric alarms)."
  default     = ""
}

variable "ecs_service_name" {
  type        = string
  description = "ECS service name (used for CPU/memory metric alarms)."
  default     = ""
}

variable "alarm_email" {
  type        = string
  description = "Email address for CloudWatch alarm notifications. Leave empty to skip SNS topic."
  default     = ""
}

variable "cpu_alarm_threshold" {
  type        = number
  description = "ECS CPU utilisation % that triggers the alarm."
  default     = 80
}

variable "memory_alarm_threshold" {
  type        = number
  description = "ECS memory utilisation % that triggers the alarm."
  default     = 85
}
