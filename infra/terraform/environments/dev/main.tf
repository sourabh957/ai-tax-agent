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

# ── CloudWatch (creates log groups before ECS, which needs the group name) ────

module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project     = var.project
  environment = var.environment

  log_retention_days = 7 # Shorter retention in dev to reduce storage costs

  # Wire ECS alarms once ECS is deployed
  ecs_cluster_name = module.ecs.cluster_name
  ecs_service_name = module.ecs.service_name

  # Set alarm_email in dev.tfvars to receive alarm notifications
  alarm_email = var.alarm_email
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

# ── RDS ───────────────────────────────────────────────────────────────────────
# COST WARNING: RDS db.t3.micro = ~$15/month. Stop or snapshot when not in use.

module "rds" {
  source = "../../modules/rds"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  vpc_id                = module.networking.vpc_id
  private_subnet_ids    = module.networking.private_subnet_ids
  rds_security_group_id = module.networking.rds_security_group_id

  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password

  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  multi_az              = false
  deletion_protection   = false
  skip_final_snapshot   = true
  backup_retention_days = 1
}

# ── ECS / Fargate ─────────────────────────────────────────────────────────────
# COST WARNING: Fargate 512 CPU / 1024 MB = ~$15/month if always running.
# Set desired_count = 0 when not in use to stop charges.

module "ecs" {
  source = "../../modules/ecs"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  vpc_id                      = module.networking.vpc_id
  subnet_ids                  = module.networking.public_subnet_ids
  ecs_tasks_security_group_id = module.networking.ecs_tasks_security_group_id

  ecr_repository_url     = module.ecr.repository_url
  image_tag              = var.image_tag
  ecs_execution_role_arn = module.iam.ecs_execution_role_arn
  ecs_task_role_arn      = module.iam.ecs_task_role_arn
  cloudwatch_log_group   = module.cloudwatch.app_log_group_name

  task_cpu      = 512
  task_memory   = 1024
  desired_count = var.ecs_desired_count

  assign_public_ip = true # Required for public subnets without NAT

  container_environment = [
    { name = "APP_ENV", value = var.environment },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "LLM_PROVIDER", value = "bedrock" },
  ]

  container_secrets = [
    {
      name      = "DATABASE_URL"
      valueFrom = module.rds.db_credentials_secret_arn
    },
  ]
}
