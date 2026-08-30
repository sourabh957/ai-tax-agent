variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "image_retention_count" {
  type        = number
  description = "Number of tagged images to retain in ECR. Older images are deleted automatically."
  default     = 10
  # Cost: ECR storage is ~$0.10/GB/month. Lifecycle policy prevents unbounded growth.
}
