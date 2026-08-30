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
  description = "VPC ID."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for ECS tasks. Use public subnets in dev (no NAT Gateway cost)."
}

variable "ecs_tasks_security_group_id" {
  type        = string
  description = "Security group ID for ECS tasks."
}

variable "ecr_repository_url" {
  type        = string
  description = "ECR repository URL for the Docker image."
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy."
  default     = "latest"
}

variable "ecs_execution_role_arn" {
  type        = string
  description = "ECS execution role ARN (for ECR pull + CloudWatch logs)."
}

variable "ecs_task_role_arn" {
  type        = string
  description = "ECS task role ARN (for application AWS API calls)."
}

variable "cloudwatch_log_group" {
  type        = string
  description = "CloudWatch log group name for ECS task logs."
}

variable "task_cpu" {
  type        = number
  description = <<-EOT
    Fargate task CPU units (256=0.25vCPU, 512=0.5vCPU, 1024=1vCPU).

    COST: ~$0.04048/vCPU/hour for Fargate in ap-south-1.
    256 CPU = ~$0.01/hour = ~$7.30/month if always running.
    Stop the service when not needed in dev to reduce costs.
  EOT
  default     = 512
}

variable "task_memory" {
  type        = number
  description = "Fargate task memory in MiB (512, 1024, 2048)."
  default     = 1024
}

variable "desired_count" {
  type        = number
  description = "Number of ECS task instances. Set to 0 to stop all tasks (zero cost)."
  default     = 1
}

variable "container_port" {
  type        = number
  description = "Port the FastAPI container listens on."
  default     = 8000
}

variable "assign_public_ip" {
  type        = bool
  description = "Assign public IP to ECS tasks. Required when using public subnets without NAT."
  default     = true
}

# Environment variables passed to the container at runtime
# These are NON-SECRET values only. Secrets come from Secrets Manager.
variable "container_environment" {
  type = list(object({
    name  = string
    value = string
  }))
  description = "Non-secret environment variables for the container."
  default     = []
}

# Secrets from Secrets Manager injected as environment variables
variable "container_secrets" {
  type = list(object({
    name      = string
    valueFrom = string # ARN of Secrets Manager secret or Parameter Store param
  }))
  description = "Secrets to inject as environment variables from Secrets Manager."
  default     = []
}
