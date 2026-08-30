output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS Fargate tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "rds_security_group_id" {
  description = "Security group ID for RDS (accepts connections from ECS only)"
  value       = aws_security_group.rds.id
}

output "nat_gateway_id" {
  description = "NAT Gateway ID (empty if not created)"
  value       = var.create_nat_gateway ? aws_nat_gateway.main[0].id : ""
}
