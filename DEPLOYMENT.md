# AWS Deployment Guide

Deploy the LazyPrices Advisor Dashboard on a single EC2 instance using Docker Compose for containerization and Terraform for infrastructure provisioning.

## Architecture

```
                  ┌─────────────────────────────────────────┐
                  │          EC2 Instance (t3.small)         │
                  │                                         │
User ──HTTP:80──► │  Nginx ──/api/──► Flask/Gunicorn :5001  │ ──► OpenAI API
                  │    │                   │                 │ ──► SEC EDGAR
                  │    │              ┌────┴────┐            │ ──► Yahoo Finance
                  │  React SPA    SQLite    ChromaDB         │
                  │  (static)   (Docker volume)              │
                  └─────────────────────────────────────────┘
```

**Estimated cost:** ~$15/month (t3.small on-demand).

## Prerequisites

| Requirement | How to get it |
|---|---|
| AWS CLI | `brew install awscli` (macOS) or [install guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| Terraform >= 1.0 | `brew install terraform` (macOS) or [install guide](https://developer.hashicorp.com/terraform/install) |
| AWS credentials | Run `aws configure` with your Access Key, Secret Key, region |
| EC2 key pair | See [Creating a Key Pair](#creating-a-key-pair) below |
| Git repo (public) | Push your code to GitHub so the EC2 instance can clone it |

## Creating a Key Pair

```bash
mkdir -p ~/.ssh

aws ec2 create-key-pair \
    --key-name my-ec2-keypair \
    --query 'KeyMaterial' \
    --output text > ~/.ssh/my-ec2-keypair.pem

chmod 400 ~/.ssh/my-ec2-keypair.pem
```

## Step 1: Configure AWS Credentials

```bash
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1), Output (json)
```

Verify it works:

```bash
aws sts get-caller-identity
```

If using **AWS Academy / Learner Lab**, credentials expire every few hours. Refresh them from the lab portal and re-run `aws configure` before each Terraform operation.

## Step 2: Configure Terraform Variables

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

| Variable | Example | Description |
|---|---|---|
| `aws_region` | `"us-east-1"` | AWS region |
| `instance_type` | `"t3.small"` | 2 vCPU, 2 GB RAM |
| `key_name` | `"my-ec2-keypair"` | Name of your EC2 key pair |
| `allowed_ssh_cidr` | `"73.45.12.99/32"` | Your public IP (`curl -s ifconfig.me`) with `/32` |
| `openai_api_key` | `"sk-..."` | Stored securely in AWS SSM Parameter Store |
| `git_repo_url` | `"https://github.com/..."` | Must be accessible from EC2 (public repo or use token) |

**IMPORTANT:** `terraform.tfvars` contains secrets and is excluded from git via `.gitignore`. Never commit it.

## Step 3: Deploy

```bash
cd deploy/terraform
terraform init        # one-time: downloads AWS provider
terraform plan        # preview what will be created
terraform apply       # type "yes" to confirm
```

Terraform creates: VPC security group, IAM role, SSM parameter, EC2 instance, and Elastic IP.

After completion, it outputs:

```
app_url     = "http://<ELASTIC_IP>"
public_ip   = "<ELASTIC_IP>"
ssh_command = "ssh -i ~/.ssh/my-ec2-keypair.pem ec2-user@<ELASTIC_IP>"
```

## Step 4: Wait for Bootstrap (3-5 minutes)

The EC2 user-data script automatically installs Docker, Docker Compose, Buildx, clones the repo, fetches secrets from SSM, and starts the containers.

Monitor progress:

```bash
ssh -i ~/.ssh/my-ec2-keypair.pem ec2-user@<ELASTIC_IP>
tail -f /var/log/user-data.log
```

Look for: `=== LazyPrices bootstrap completed ===`

Verify containers are running:

```bash
cd /opt/lazyprices/deploy/docker
sudo docker compose ps
```

You should see `lazyprices-backend` and `lazyprices-frontend` both running.

## Step 5: Open the Dashboard

Navigate to `http://<ELASTIC_IP>` in your browser. The dashboard loads but has no data until you run the pipeline.

## Step 6: Run the Data Pipeline

```bash
ssh -i ~/.ssh/my-ec2-keypair.pem ec2-user@<ELASTIC_IP>
cd /opt/lazyprices/deploy/docker

# Process ALL companies (29 DJIA tickers) -- takes 15-30+ minutes
sudo docker compose --profile pipeline run --rm pipeline

# Or process specific companies
sudo docker compose --profile pipeline run --rm pipeline --ciks 320193           # Apple only
sudo docker compose --profile pipeline run --rm pipeline --ciks 320193,19617     # Apple + JPMorgan

# Limit filings per company (default is 5)
sudo docker compose --profile pipeline run --rm pipeline --max-filings 3

# Force reprocessing of already-processed filings
sudo docker compose --profile pipeline run --rm pipeline --force
```

You can also trigger the pipeline from the dashboard UI using the "Process" button on unprocessed tickers.

---

## Redeploying After Code Changes

From your local machine:

```bash
# 1. Commit and push
git add .
git commit -m "description of changes"
git push origin 10K_data-extraction

# 2. SSH into instance, pull, and rebuild
ssh -i ~/.ssh/my-ec2-keypair.pem ec2-user@<ELASTIC_IP>
cd /opt/lazyprices
sudo git pull
cd deploy/docker
sudo docker compose up -d --build
```

Docker only rebuilds layers that changed, so this is fast for small changes.

### When to also re-run the pipeline

| What changed | Rebuild containers | Re-run pipeline |
|---|---|---|
| Frontend (React components, CSS) | Yes | No |
| Backend (Flask routes, chat) | Yes | No |
| Pipeline logic (similarity, LAS, embeddings) | Yes | Yes (`--force`) |
| `config.py` (LAS weights, normalization) | Yes | Yes (`--force`) |
| `requirements.txt` or `package.json` | Yes | No |
| Terraform only (security group, instance type) | No (run `terraform apply` locally) | No |

## Data Persistence

The application uses two persistent Docker volumes:

### PostgreSQL (`postgres-data` volume)
Stores all structured data: filings, LAS scores, pipeline runs, and client profiles. PostgreSQL runs as a dedicated container and persists data independently from the application containers.

### File data (`lazyprices-data` volume)
Stores file-based assets:
- ChromaDB (`data/vectordb/`) -- RAG vector embeddings
- Sparse vectors (`data/vectors/`)
- Downloaded filings (`data/filings/`)

### Database engine selection
- **Docker (production):** PostgreSQL is used automatically via the `DATABASE_URL` environment variable injected by docker-compose
- **Local dev (no Docker):** SQLite is used as a fallback when `DATABASE_URL` is not set

Data **survives**:
- Container rebuilds (`docker compose up -d --build`)
- Container restarts (`docker compose restart`)
- Instance reboots

Data **is lost if**:
- You run `terraform destroy` (terminates instance + all volumes)
- You run `docker compose down -v` (the `-v` flag deletes volumes)
- Note: `docker compose down` (without `-v`) preserves all data

## Tearing Down

```bash
cd deploy/terraform
terraform destroy    # type "yes" to confirm
```

This removes all AWS resources: EC2 instance, Elastic IP, security group, IAM role, and SSM parameter. All data on the instance is permanently deleted.

## Troubleshooting

### SSH times out

- Verify `allowed_ssh_cidr` matches your current IP: `curl -s ifconfig.me`
- Run `terraform apply` after updating `terraform.tfvars`
- If on a university/corporate network, port 22 may be blocked -- try a phone hotspot

### AWS credentials expired

- Common with AWS Academy/Learner Lab (sessions expire every few hours)
- Get fresh credentials from your lab portal and re-run `aws configure`
- Verify: `aws sts get-caller-identity`

### Docker build fails with "requires buildx"

```bash
# Install buildx on the instance
sudo curl -SL "https://github.com/docker/buildx/releases/latest/download/buildx-$(curl -s https://api.github.com/repos/docker/buildx/releases/latest | grep tag_name | cut -d'"' -f4).linux-amd64" \
    -o /usr/local/lib/docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
```

### Git clone fails on EC2

- If your repo is **private**, the automated clone won't work
- Either make the repo public, or clone manually with a GitHub token:
  ```bash
  sudo git clone https://<GITHUB_TOKEN>@github.com/user/repo.git /opt/lazyprices
  ```

### No default VPC found

```bash
aws ec2 create-default-vpc --region us-east-1
```

### Containers not running after bootstrap

```bash
# Check logs
sudo docker compose -f /opt/lazyprices/deploy/docker/docker-compose.yml logs

# Check bootstrap log
cat /var/log/user-data.log
```

## Local Docker Testing

Test the full stack locally before deploying to AWS:

```bash
# Create .env at project root
echo "OPENAI_API_KEY=sk-..." > .env

# Build and start
cd deploy/docker
docker compose up -d --build

# Open http://localhost in your browser

# Run the pipeline locally
docker compose --profile pipeline run --rm pipeline --ciks 320193

# Stop everything
docker compose down
```

## File Reference

```
deploy/
├── docker/
│   ├── Dockerfile.backend      # Python 3.10 + Gunicorn
│   ├── Dockerfile.frontend     # Node 18 build + Nginx
│   ├── docker-compose.yml      # backend, frontend, pipeline services
│   └── nginx.conf              # Static files + /api reverse proxy
├── terraform/
│   ├── main.tf                 # EC2, SG, IAM, SSM, EIP
│   ├── variables.tf            # Input variables
│   ├── outputs.tf              # IP, URL, SSH command
│   └── terraform.tfvars.example
├── scripts/
│   └── user_data.sh            # EC2 first-boot script
└── README.md
```

## Adding HTTPS (Optional)

Requires a domain name pointed at your Elastic IP:

```bash
ssh -i ~/.ssh/my-ec2-keypair.pem ec2-user@<ELASTIC_IP>
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```
