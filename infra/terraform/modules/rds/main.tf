locals {
  name_prefix = "${var.project}-${var.environment}"
}

# ── DB Subnet Group ───────────────────────────────────────────────────────────
# RDS runs in private subnets only — never publicly accessible.

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "${local.name_prefix}-db-subnet-group"
    Project     = var.project
    Environment = var.environment
  }
}

# ── RDS PostgreSQL Instance ───────────────────────────────────────────────────

resource "aws_db_instance" "postgres" {
  identifier = "${local.name_prefix}-postgres"

  # Engine
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = var.instance_class

  # Storage
  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.allocated_storage * 2 # autoscaling ceiling
  storage_type          = "gp2"
  storage_encrypted     = true

  # Credentials — supplied via variables, stored in Secrets Manager post-apply
  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  # Networking — private, never publicly accessible
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_security_group_id]
  publicly_accessible    = false

  # Availability
  multi_az = var.multi_az

  # Backups
  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  # Protection
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
  final_snapshot_identifier = (
    var.skip_final_snapshot ? null : "${local.name_prefix}-final-snapshot"
  )

  # Performance Insights (free tier: 7 days retention)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  tags = {
    Name        = "${local.name_prefix}-postgres"
    Project     = var.project
    Environment = var.environment
  }
}

# ── Secrets Manager: store DB credentials ────────────────────────────────────
# The ECS task reads the DB connection string from Secrets Manager.
# The actual password value must be set OUTSIDE Terraform to avoid
# storing secrets in tfstate.

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${local.name_prefix}/db-credentials"
  description = "RDS PostgreSQL credentials for ${local.name_prefix}"

  # Allow immediate deletion in dev; set recovery window in prod
  recovery_window_in_days = 0

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# NOTE: We create the secret container here but do NOT set the value in Terraform.
# Set the secret value manually after apply:
#
#   aws secretsmanager put-secret-value \
#     --secret-id "<project>-<env>/db-credentials" \
#     --secret-string '{"username":"...","password":"...","host":"...","port":"5432","dbname":"tax_agent"}'
#
# This prevents credentials from ever appearing in terraform.tfstate or plan output.
