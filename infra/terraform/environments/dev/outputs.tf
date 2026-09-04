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

output "ec2_sg_id" {
  description = "EC2 public security group ID"
  value       = module.security.ec2_sg_id
}

output "rds_sg_id" {
  description = "RDS security group ID"
  value       = module.security.rds_sg_id
}

output "s3_bucket_name" {
  description = "S3 bucket name for tax documents"
  value       = module.s3.bucket_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push and the EC2-hosted containers"
  value       = module.ecr.repository_url
}

output "db_host" {
  description = "RDS instance hostname"
  value       = module.rds.db_host
}

output "ec2_public_ip" {
  description = "Public IP address of the EC2 Spot instance (changes on instance replacement)"
  value       = module.ec2.public_ip
}

output "elastic_ip" {
  description = "Elastic IP — static public address for the application (does NOT change)"
  value       = aws_eip.app.public_ip
}

output "elastic_ip_allocation_id" {
  description = "Elastic IP allocation ID — needed to re-associate after instance replacement"
  value       = aws_eip.app.id
}

output "launch_template_id" {
  description = "EC2 Launch Template ID for spinning up a replacement instance"
  value       = aws_launch_template.app.id
}

output "launch_template_name" {
  description = "EC2 Launch Template name"
  value       = aws_launch_template.app.name
}

output "ec2_instance_id" {
  description = "EC2 Spot instance ID"
  value       = module.ec2.instance_id
}

output "app_log_group" {
  description = "CloudWatch log group for application logs"
  value       = module.cloudwatch.app_log_group_name
}

# ── Secrets Manager outputs (ARNs only — never values) ───────────────────────

output "db_credentials_secret_arn" {
  description = "Secrets Manager ARN for DB credentials (set value with AWS CLI post-apply)"
  value       = module.secrets.db_credentials_secret_arn
}

output "db_credentials_secret_name" {
  description = "Secrets Manager name for DB credentials"
  value       = module.secrets.db_credentials_secret_name
}

output "qdrant_api_key_secret_arn" {
  description = "Secrets Manager ARN for Qdrant API key (set value with AWS CLI post-apply)"
  value       = module.secrets.qdrant_api_key_secret_arn
}

output "oidc_credentials_secret_arn" {
  description = "Secrets Manager ARN for OIDC client secret (set value with AWS CLI post-apply)"
  value       = module.secrets.oidc_credentials_secret_arn
}

output "secrets_read_policy_arn" {
  description = "IAM policy granting EC2 instance read access to application secrets"
  value       = module.secrets.secrets_read_policy_arn
}