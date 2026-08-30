variable "project" {
  type        = string
  description = "Project name prefix."
}

variable "environment" {
  type        = string
  description = "Deployment environment."
}

variable "s3_bucket_arn" {
  type        = string
  description = "ARN of the S3 bucket the ECS task role needs access to."
  default     = ""
}

variable "aws_region" {
  type        = string
  description = "AWS region (used to scope Bedrock permissions)."
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID (used to scope Bedrock permissions)."
  default     = ""
  # If empty, Bedrock access is granted to all models in the region.
  # Provide the account ID to tighten the scope.
}

variable "bedrock_model_ids" {
  type        = list(string)
  description = "Bedrock model IDs the ECS task is allowed to invoke."
  default     = ["anthropic.claude-*", "amazon.titan-embed-*"]
}
