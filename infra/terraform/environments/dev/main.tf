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
  # The single EC2 Spot instance runs in a public subnet, so NAT is not needed.
  create_nat_gateway = false
}

# ── Security Groups ───────────────────────────────────────────────────────────

module "security" {
  source = "../../modules/security"

  vpc_id      = module.networking.vpc_id
  project     = var.project
  environment = var.environment

  # Restrict to your IP/CIDR in production or whenever possible.
  ssh_allowed_cidr = var.ssh_allowed_cidr
}

# ── CloudWatch (creates log groups consumed by the EC2-hosted containers) ─────

module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project     = var.project
  environment = var.environment

  log_retention_days = 7 # Shorter retention in dev to reduce storage costs

  # ECS alarms are intentionally disabled in the EC2 Spot architecture.
  ecs_cluster_name = ""
  ecs_service_name = ""

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
# COST WARNING: RDS db.t4g.micro is one of the lowest-cost PostgreSQL options.

module "rds" {
  source = "../../modules/rds"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  vpc_id                = module.networking.vpc_id
  private_subnet_ids    = module.networking.private_subnet_ids
  rds_security_group_id = module.security.rds_sg_id

  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password

  instance_class        = "db.t4g.micro"
  allocated_storage     = 20
  multi_az              = false
  deletion_protection   = false
  skip_final_snapshot   = true
  backup_retention_days = 1
}

# ── EC2 Spot Instance ─────────────────────────────────────────────────────────
# Replaces ECS/Fargate with a single low-cost public EC2 Spot host.

module "ec2" {
  source = "../../modules/ec2"

  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = module.networking.public_subnet_ids[0]
  security_group_id    = module.security.ec2_sg_id
  iam_instance_profile = module.iam.ec2_instance_profile_name
  domain_name          = var.domain_name
  ami_id               = ""
  cloudwatch_log_group = module.cloudwatch.app_log_group_name

  # Placeholder image references. If you keep a single ECR repo, publish
  # distinct tags such as frontend-latest and api-latest.
  ecr_repository_urls = {
    frontend = module.ecr.repository_url
    api      = module.ecr.repository_url
  }
}

# ── Secrets Manager ───────────────────────────────────────────────────────────
# Creates secret containers for DB credentials, Qdrant API key, and OIDC secret.
# The EC2 instance role (module.iam) reads these at runtime — no keys in env.
#
# Recommended: leave db_username/db_password/qdrant_api_key/oidc_client_secret
# empty here and set them post-apply via:
#   aws secretsmanager put-secret-value --secret-id ... --secret-string '...'
# This keeps secrets out of tfstate.

module "secrets" {
  source = "../../modules/secrets"

  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region

  # DB components — used to build the secret JSON (leave empty to set out-of-band)
  db_host     = module.rds.db_host
  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password

  # These should ALWAYS be set out-of-band, not in tfvars
  qdrant_api_key     = ""
  oidc_client_secret = ""

  # Allow immediate deletion in dev; use 7-30 in prod
  recovery_window_days = 0
}

# Attach the secrets read policy to the EC2 instance role
resource "aws_iam_role_policy_attachment" "ec2_secrets_read" {
  role       = module.iam.ec2_instance_role_name
  policy_arn = module.secrets.secrets_read_policy_arn
}
