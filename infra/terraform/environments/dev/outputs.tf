output "aws_region" {
  description = "AWS region in use"
  value       = var.aws_region
}

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "aws_account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "ecs_tasks_sg_id" {
  description = "ECS tasks security group ID"
  value       = module.networking.ecs_tasks_security_group_id
}

output "s3_bucket_name" {
  description = "S3 bucket name for tax documents"
  value       = module.s3.bucket_name
}

output "ecs_execution_role_arn" {
  description = "ECS execution role ARN"
  value       = module.iam.ecs_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN"
  value       = module.iam.ecs_task_role_arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push and ECS task definition"
  value       = module.ecr.repository_url
}

output "db_host" {
  description = "RDS instance hostname"
  value       = module.rds.db_host
}

output "db_credentials_secret_arn" {
  description = "Secrets Manager ARN for DB credentials"
  value       = module.rds.db_credentials_secret_arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.ecs.service_name
}

output "app_log_group" {
  description = "CloudWatch log group for application logs"
  value       = module.cloudwatch.app_log_group_name
}