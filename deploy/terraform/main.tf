terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------- Networking (default VPC) ----------

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------- AMI ----------

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ---------- Security Group ----------

resource "aws_security_group" "lazyprices" {
  name_prefix = "lazyprices-"
  description = "LazyPrices dashboard - HTTP, HTTPS, SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "lazyprices" }
}

# ---------- SSM Parameter (OpenAI API key) ----------

resource "aws_ssm_parameter" "openai_api_key" {
  name  = "/lazyprices/openai-api-key"
  type  = "SecureString"
  value = var.openai_api_key

  tags = { Project = "lazyprices" }
}

# ---------- IAM Role (SSM read access) ----------

resource "aws_iam_role" "ec2" {
  name_prefix = "lazyprices-ec2-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Project = "lazyprices" }
}

resource "aws_iam_role_policy" "ssm_read" {
  name_prefix = "ssm-read-"
  role        = aws_iam_role.ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = [aws_ssm_parameter.openai_api_key.arn]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name_prefix = "lazyprices-"
  role        = aws_iam_role.ec2.name
}

# ---------- EC2 Instance ----------

resource "aws_instance" "lazyprices" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.lazyprices.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/../scripts/user_data.sh", {
    aws_region   = var.aws_region
    git_repo_url = var.git_repo_url
  })

  tags = { Name = "lazyprices-dashboard" }
}

# ---------- Elastic IP ----------

resource "aws_eip" "lazyprices" {
  instance = aws_instance.lazyprices.id
  domain   = "vpc"

  tags = { Name = "lazyprices-dashboard" }
}
