variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.small = 2 vCPU, 2 GB RAM)"
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "Name of an existing EC2 key pair for SSH access"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the instance (e.g. 203.0.113.5/32)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "openai_api_key" {
  description = "OpenAI API key — stored in SSM Parameter Store as SecureString"
  type        = string
  sensitive   = true
}

variable "git_repo_url" {
  description = "Git repository URL to clone onto the EC2 instance"
  type        = string
  default     = "https://github.com/your-org/TIAA2_Capstone_Project.git"
}
