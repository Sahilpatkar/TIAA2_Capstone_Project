output "public_ip" {
  description = "Elastic IP address of the instance"
  value       = aws_eip.lazyprices.public_ip
}

output "app_url" {
  description = "Dashboard URL"
  value       = "http://${aws_eip.lazyprices.public_ip}"
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ec2-user@${aws_eip.lazyprices.public_ip}"
}
