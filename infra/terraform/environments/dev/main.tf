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
# Single public Spot host: Nginx → Docker Compose (api + frontend containers).
# user_data fetches secrets from Secrets Manager at every boot — no secrets in Terraform.

module "ec2" {
  source = "../../modules/ec2"

  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = module.networking.public_subnet_ids[1]  # ap-south-1b — more Spot capacity
  security_group_id    = module.security.ec2_sg_id
  iam_instance_profile = module.iam.ec2_instance_profile_name
  domain_name          = var.domain_name
  ami_id               = ""
  cloudwatch_log_group = module.cloudwatch.app_log_group_name

  # Single ECR repo — two tags: api-latest and frontend-latest
  ecr_repository_urls = {
    api      = module.ecr.repository_url
    frontend = module.ecr.repository_url
  }

  # Secrets Manager secret names — resolved at EC2 boot time, NOT baked into the image
  db_secret_name     = module.secrets.db_credentials_secret_name
  qdrant_secret_name = module.secrets.qdrant_api_key_secret_name

  # Non-secret runtime config baked into user_data
  s3_bucket_name    = module.s3.bucket_name
  bedrock_model_id  = "anthropic.claude-3-5-sonnet-20241022-v2:0"
  qdrant_url        = var.qdrant_url
  qdrant_collection = "tax_rules"
  elastic_ip        = aws_eip.app.public_ip

  depends_on = [module.secrets, aws_eip.app]
}

# ── Elastic IP — static public address for the application host ───────────────
# Survives instance replacement (Spot interruption or terraform apply).
# Association is re-made automatically when a new instance is created.

resource "aws_eip" "app" {
  domain = "vpc"

  tags = {
    Name        = "${var.project}-${var.environment}-app-eip"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_eip_association" "app" {
  instance_id   = module.ec2.instance_id
  allocation_id = aws_eip.app.id
}

# ── EC2 Launch Template — reusable template for instance recovery ─────────────
# Captures the full instance config so a new identical instance can be launched
# in one CLI command if the Spot instance is interrupted or terminated.
# Usage:  aws ec2 run-instances --launch-template LaunchTemplateId=<id>,Version=$Latest
#         Then associate the EIP with the new instance ID.

resource "aws_launch_template" "app" {
  name_prefix   = "${var.project}-${var.environment}-"
  description   = "Taxly ${var.environment} application host — auto-bootstraps via user_data"
  image_id      = module.ec2.ami_id
  instance_type = var.instance_type
  key_name      = var.key_name != "" ? var.key_name : null

  iam_instance_profile {
    name = module.iam.ec2_instance_profile_name
  }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [module.security.ec2_sg_id]
    subnet_id                   = module.networking.public_subnet_ids[1]  # same AZ as EC2
    delete_on_termination       = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name        = "taxly-spot-instance"
      Project     = var.project
      Environment = var.environment
    }
  }

  tags = {
    Name        = "${var.project}-${var.environment}-launch-template"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
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
