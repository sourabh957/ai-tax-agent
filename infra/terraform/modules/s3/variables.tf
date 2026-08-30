variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name for tax documents. Must be globally unique."
  default     = ""
  # If empty, a name is generated: {project}-{environment}-documents-{random}
}

variable "enable_versioning" {
  type        = bool
  description = "Enable S3 object versioning (recommended for production)."
  default     = false
  # Cost: versioning retains old object versions; add lifecycle rules to control costs.
}

variable "lifecycle_expire_days" {
  type        = number
  description = "Days after which non-current object versions are deleted. 0 = disabled."
  default     = 90
}
