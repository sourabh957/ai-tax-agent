output "aws_region" {
  description = "AWS region in use"
  value       = var.aws_region
}

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (ECS tasks run here in dev)"
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
  description = "ECR repository URL - use for docker push and ECS task definition"
  value       = module.ecr.repository_url
}

output "aws_account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}
