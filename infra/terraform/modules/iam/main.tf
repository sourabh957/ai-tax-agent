locals {
  name_prefix = "${var.project}-${var.environment}"
}

# ── ECS Execution Role ────────────────────────────────────────────────────────
# Used by ECS to pull the Docker image from ECR and push logs to CloudWatch.
# This role is assumed by the ECS service itself — not the application.

data "aws_iam_policy_document" "ecs_execution_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_execution_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# AWS-managed policy: allows ECR pull + CloudWatch logs
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}


# ── ECS Task Role ─────────────────────────────────────────────────────────────
# Used by the running application container.
# Grants ONLY the permissions the application needs — least privilege.

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task" {
  name               = "${local.name_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# Task policy: S3 + Bedrock + CloudWatch Logs + Secrets Manager
data "aws_iam_policy_document" "ecs_task_policy" {
  # ── S3: read/write only to the documents bucket ─────────────────────────────
  dynamic "statement" {
    for_each = var.s3_bucket_arn != "" ? [1] : []
    content {
      sid    = "S3DocumentAccess"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      resources = [
        var.s3_bucket_arn,
        "${var.s3_bucket_arn}/*",
      ]
    }
  }

  # ── Bedrock: invoke foundation models ───────────────────────────────────────
  statement {
    sid    = "BedrockInvokeModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    # Scope to specific models if account ID is provided
    resources = var.aws_account_id != "" ? [
      for model_id in var.bedrock_model_ids :
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${model_id}"
    ] : ["arn:aws:bedrock:${var.aws_region}::foundation-model/*"]
  }

  # ── CloudWatch Logs: emit structured logs ────────────────────────────────────
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:*:log-group:/ecs/${local.name_prefix}*"]
  }

  # ── Secrets Manager: read application secrets ────────────────────────────────
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${local.name_prefix}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task" {
  name   = "${local.name_prefix}-ecs-task-policy"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_policy.json
}


# ── EC2 Instance Role / Profile ───────────────────────────────────────────────
# Used by the EC2 Spot instance and the Docker containers running on it.

data "aws_iam_policy_document" "ec2_instance_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_instance" {
  name               = "${local.name_prefix}-ec2-instance-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_instance_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "ec2_instance_policy" {
  dynamic "statement" {
    for_each = var.s3_bucket_arn != "" ? [1] : []
    content {
      sid    = "S3DocumentAccess"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      resources = [
        var.s3_bucket_arn,
        "${var.s3_bucket_arn}/*",
      ]
    }
  }

  statement {
    sid    = "BedrockInvokeModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = var.aws_account_id != "" ? [
      for model_id in var.bedrock_model_ids :
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${model_id}"
    ] : ["arn:aws:bedrock:${var.aws_region}::foundation-model/*"]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:*:log-group:/ecs/${local.name_prefix}*"]
  }

  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${local.name_prefix}/*",
    ]
  }

  statement {
    sid    = "EcrPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetAuthorizationToken",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ec2_instance" {
  name   = "${local.name_prefix}-ec2-instance-policy"
  role   = aws_iam_role.ec2_instance.id
  policy = data.aws_iam_policy_document.ec2_instance_policy.json
}

resource "aws_iam_instance_profile" "ec2_instance" {
  name = "${local.name_prefix}-ec2-instance-profile"
  role = aws_iam_role.ec2_instance.name

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}
