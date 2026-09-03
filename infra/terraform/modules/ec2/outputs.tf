output "instance_id" {
  description = "EC2 Spot instance ID"
  value       = aws_instance.spot.id
}

output "public_ip" {
  description = "Public IP address of the EC2 Spot instance"
  value       = aws_instance.spot.public_ip
}

output "public_dns" {
  description = "Public DNS name of the EC2 Spot instance"
  value       = aws_instance.spot.public_dns
}
