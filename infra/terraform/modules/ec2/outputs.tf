output "instance_id" {
  description = "EC2 Spot instance ID"
  value       = aws_instance.spot.id
}

output "ami_id" {
  description = "AMI ID used by this instance (for the Launch Template)"
  value       = aws_instance.spot.ami
}

output "public_ip" {
  description = "Public IP address of the EC2 Spot instance"
  value       = aws_instance.spot.public_ip
}

output "public_dns" {
  description = "Public DNS name of the EC2 Spot instance"
  value       = aws_instance.spot.public_dns
}
