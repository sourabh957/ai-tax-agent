output "ec2_sg_id" {
  description = "Security group ID for the public EC2 Spot instance"
  value       = aws_security_group.ec2_public.id
}

output "rds_sg_id" {
  description = "Security group ID for the private RDS instance"
  value       = aws_security_group.rds.id
}
