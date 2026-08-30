output "app_log_group_name" {
  description = "CloudWatch log group name for application logs"
  value       = aws_cloudwatch_log_group.app.name
}

output "agent_traces_log_group_name" {
  description = "CloudWatch log group name for agent traces"
  value       = aws_cloudwatch_log_group.agent_traces.name
}

output "alarms_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms (empty if alarm_email not set)"
  value       = var.alarm_email != "" ? aws_sns_topic.alarms[0].arn : ""
}
