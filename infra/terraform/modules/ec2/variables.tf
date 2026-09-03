variable "instance_type" {
  type        = string
  description = "EC2 Spot instance type for the application host."
  default     = "t4g.small"
}

variable "key_name" {
  type        = string
  description = "Existing EC2 key pair name used for SSH access."
  default     = ""
}

variable "subnet_id" {
  type        = string
  description = "Public subnet ID where the EC2 Spot instance will run."
}

variable "security_group_id" {
  type        = string
  description = "Security group ID attached to the EC2 Spot instance."
}

variable "iam_instance_profile" {
  type        = string
  description = "IAM instance profile name attached to the EC2 Spot instance."
}

variable "ecr_repository_urls" {
  type        = map(string)
  description = "ECR repository URLs keyed by service name (for example frontend, api)."
  default     = {}
}

variable "cloudwatch_log_group" {
  type        = string
  description = "CloudWatch log group name used by the Docker awslogs log driver."
  default     = "/ecs/taxly"
}

variable "domain_name" {
  type        = string
  description = "Domain name served by Nginx."
  default     = ""
}

variable "ami_id" {
  type        = string
  description = "Optional AMI ID override. Leave empty to use the latest Amazon Linux 2023 AMI."
  default     = ""
}
