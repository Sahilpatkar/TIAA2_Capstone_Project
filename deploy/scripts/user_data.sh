#!/bin/bash
set -euo pipefail

exec > /var/log/user-data.log 2>&1
echo "=== LazyPrices bootstrap started at $(date) ==="

# ---- Install Docker ----
dnf update -y
dnf install -y docker git

systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

# ---- Install Docker Compose + Buildx plugins ----
mkdir -p /usr/local/lib/docker/cli-plugins
ARCH=$(uname -m)
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$${ARCH}" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

BUILDX_VERSION=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest | grep tag_name | cut -d'"' -f4)
curl -SL "https://github.com/docker/buildx/releases/download/$${BUILDX_VERSION}/buildx-$${BUILDX_VERSION}.linux-amd64" \
    -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

# ---- Clone project ----
git clone ${git_repo_url} /opt/lazyprices || true
cd /opt/lazyprices

# ---- Fetch OpenAI API key from SSM Parameter Store ----
OPENAI_KEY=$(aws ssm get-parameter \
    --region ${aws_region} \
    --name /lazyprices/openai-api-key \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text 2>/dev/null || echo "")

if [ -n "$OPENAI_KEY" ]; then
    echo "OPENAI_API_KEY=$OPENAI_KEY" > /opt/lazyprices/.env
    echo "Wrote .env with OPENAI_API_KEY"
else
    touch /opt/lazyprices/.env
    echo "WARNING: Could not fetch OPENAI_API_KEY from SSM"
fi

# ---- Create persistent data directories ----
mkdir -p /opt/lazyprices/data/vectordb \
         /opt/lazyprices/data/vectors \
         /opt/lazyprices/data/filings

# ---- Build and start services ----
cd /opt/lazyprices/deploy/docker
docker compose up -d --build

# ---- Set ownership so ec2-user can manage later ----
chown -R ec2-user:ec2-user /opt/lazyprices

echo "=== LazyPrices bootstrap completed at $(date) ==="
