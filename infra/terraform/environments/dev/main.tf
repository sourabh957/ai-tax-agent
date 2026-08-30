terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Data sources ──────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# ── Networking ────────────────────────────────────────────────────────────────

module "networking" {
  source = "../../modules/networking"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  # Cost note: NAT Gateway is false by default (~$35/month if enabled).
  # ECS tasks use public subnets for dev to avoid this cost.
  create_nat_gateway = false
}

# ── S3 ────────────────────────────────────────────────────────────────────────

module "s3" {
  source = "../../modules/s3"

  project     = var.project
  environment = var.environment

  # Versioning off in dev to minimise storage costs.
  enable_versioning     = false
  lifecycle_expire_days = 30
}

# ── IAM ───────────────────────────────────────────────────────────────────────

module "iam" {
  source = "../../modules/iam"

  project        = var.project
  environment    = var.environment
  aws_region     = var.aws_region
  aws_account_id = data.aws_caller_identity.current.account_id
  s3_bucket_arn  = module.s3.bucket_arn

  bedrock_model_ids = [
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "amazon.titan-embed-text-v2:0",
  ]
}

# ── ECR ───────────────────────────────────────────────────────────────────────

module "ecr" {
  source = "../../modules/ecr"

  project               = var.project
  environment           = var.environment
  image_retention_count = 5 # Keep fewer images in dev to save storage costs
}
