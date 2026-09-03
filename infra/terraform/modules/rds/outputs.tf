output "db_endpoint" {
  description = "RDS instance endpoint (host:port)"
  value       = aws_db_instance.postgres.endpoint
}

output "db_host" {
  description = "RDS instance hostname"
  value       = aws_db_instance.postgres.address
}

output "db_port" {
  description = "RDS instance port"
  value       = aws_db_instance.postgres.port
}

output "db_name" {
  description = "PostgreSQL database name"
  value       = aws_db_instance.postgres.db_name
}

output "db_instance_id" {
  description = "RDS instance identifier"
  value       = aws_db_instance.postgres.identifier
}
