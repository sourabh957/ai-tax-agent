locals {
  name_prefix = "${var.project}-${var.environment}"
}

# ── Log Groups ────────────────────────────────────────────────────────────────

# Application logs (FastAPI + agent + RAG)
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "/ecs/${local.name_prefix}"
    Project     = var.project
    Environment = var.environment
  }
}

# Separate log group for agent traces (structured JSON)
resource "aws_cloudwatch_log_group" "agent_traces" {
  name              = "/ecs/${local.name_prefix}/agent-traces"
  retention_in_days = var.log_retention_days

  tags = {
    Name        = "/ecs/${local.name_prefix}/agent-traces"
    Project     = var.project
    Environment = var.environment
  }
}

# ── SNS Topic for alarms (optional) ──────────────────────────────────────────

resource "aws_sns_topic" "alarms" {
  count = var.alarm_email != "" ? 1 : 0
  name  = "${local.name_prefix}-alarms"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_sns_topic_subscription" "alarms_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ── ECS Metric Alarms ─────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  count = var.ecs_cluster_name != "" && var.ecs_service_name != "" ? 1 : 0

  alarm_name          = "${local.name_prefix}-ecs-cpu-high"
  alarm_description   = "ECS CPU utilisation above ${var.cpu_alarm_threshold}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = var.alarm_email != "" ? [aws_sns_topic.alarms[0].arn] : []

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  count = var.ecs_cluster_name != "" && var.ecs_service_name != "" ? 1 : 0

  alarm_name          = "${local.name_prefix}-ecs-memory-high"
  alarm_description   = "ECS memory utilisation above ${var.memory_alarm_threshold}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  alarm_actions = var.alarm_email != "" ? [aws_sns_topic.alarms[0].arn] : []

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── CloudWatch Insights Query (agent trace analysis) ─────────────────────────

resource "aws_cloudwatch_query_definition" "agent_errors" {
  name = "${local.name_prefix}/agent-errors"

  log_group_names = [aws_cloudwatch_log_group.app.name]

  query_string = <<-QUERY
    fields @timestamp, request_id, user_id, status, latency_ms, estimated_cost_usd
    | filter status = "failed" or status = "timeout"
    | sort @timestamp desc
    | limit 50
  QUERY
}

resource "aws_cloudwatch_query_definition" "high_cost_requests" {
  name = "${local.name_prefix}/high-cost-requests"

  log_group_names = [aws_cloudwatch_log_group.app.name]

  query_string = <<-QUERY
    fields @timestamp, request_id, user_id, estimated_cost_usd, total_input_tokens, total_output_tokens, iteration_count
    | filter estimated_cost_usd > 0.01
    | sort estimated_cost_usd desc
    | limit 20
  QUERY
}
