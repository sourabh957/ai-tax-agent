locals {
  repo_name = "${var.project}-${var.environment}"
}

# ── ECR Repository ────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "app" {
  name                 = local.repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true # Security: auto-scan images for known CVEs on push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name        = local.repo_name
    Project     = var.project
    Environment = var.environment
  }
}

# ── Lifecycle Policy ──────────────────────────────────────────────────────────
# Keeps the most recent N tagged images; deletes untagged images after 1 day.
# Prevents unbounded ECR storage growth and associated costs.

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last ${var.image_retention_count} tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = var.image_retention_count
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Delete untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      }
    ]
  })
}
