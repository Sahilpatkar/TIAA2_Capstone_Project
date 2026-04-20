# AWS Deployment Guide

Deploy the LazyPrices dashboard on a single EC2 instance using Docker Compose and Terraform.

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.0
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) configured with credentials
- An EC2 key pair created in your target AWS region
- Your project pushed to a Git repository accessible from the EC2 instance

## Architecture

```
EC2 (t3.small)
├── Nginx        :80   ← serves React build, proxies /api to backend
├── Flask/Gunicorn :5001 ← REST API + RAG chat
├── PostgreSQL   :5432 ← filing data, LAS scores (Docker volume)
└── ChromaDB           ← vector store (Docker volume)
```

The pipeline computes a **hybrid change intensity** for each 10-K filing pair that blends text-based similarity (cosine/Jaccard) with numerical divergence detection. This ensures that changes in financial figures (e.g. revenue shifting from $5M to $50M) are captured even when the surrounding narrative text is identical. The blend weight is controlled by `NUMERIC_CHANGE_ALPHA` in `config.py` (default 0.7 text / 0.3 numerical).

Estimated cost: ~$15/month (t3.small on-demand). Less with Reserved Instances or Spot.

## Step 1: Configure Terraform

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

| Variable           | Description                                       |
| ------------------ | ------------------------------------------------- |
| `aws_region`       | AWS region (default: `us-east-1`)                 |
| `instance_type`    | EC2 instance type (default: `t3.small`)           |
| `key_name`         | Name of your EC2 key pair                         |
| `allowed_ssh_cidr` | Your IP in CIDR notation (e.g. `203.0.113.5/32`)  |
| `openai_api_key`   | Your OpenAI API key (stored securely in SSM)      |
| `git_repo_url`     | HTTPS URL of your Git repository                  |

## Step 2: Deploy

```bash
terraform init
terraform plan      # review what will be created
terraform apply     # type "yes" to confirm
```

Terraform outputs the public IP, app URL, and SSH command when done.

The EC2 user-data script automatically:
1. Installs Docker and Docker Compose
2. Clones your repository
3. Fetches the OpenAI API key from SSM Parameter Store
4. Builds and starts the containers

Allow 3-5 minutes after `terraform apply` for the instance to finish bootstrapping.

## Step 3: Verify

```bash
# Check bootstrap progress
ssh -i ~/.ssh/<key_name>.pem ec2-user@<ELASTIC_IP>
tail -f /var/log/user-data.log

# Verify containers are running
docker compose -f /opt/lazyprices/deploy/docker/docker-compose.yml ps
```

Open `http://<ELASTIC_IP>` in your browser.

## Running the Pipeline

The data pipeline is a separate Docker Compose profile run on demand:

```bash
ssh -i ~/.ssh/<key_name>.pem ec2-user@<ELASTIC_IP>

# Process Apple (CIK 320193)
cd /opt/lazyprices/deploy/docker
docker compose --profile pipeline run --rm pipeline --ciks 320193

# Process multiple companies
docker compose --profile pipeline run --rm pipeline --ciks 320193,19617

# Force reprocess all filings (e.g. after a pipeline version bump)
docker compose --profile pipeline run --rm pipeline --ciks 320193 --force
```

The pipeline version is tracked in `config.PIPELINE_VERSION`. When bumped (e.g. from `1.2` to `1.3` after adding hybrid numerical change detection), all filings are automatically reprocessed on the next run without needing `--force`.

You can also trigger the pipeline from the dashboard UI via the "Process" button on unprocessed tickers, which calls the `/api/pipeline/run` endpoint.

## Redeploying After Code Changes

```bash
ssh -i ~/.ssh/<key_name>.pem ec2-user@<ELASTIC_IP>
cd /opt/lazyprices
git pull
cd deploy/docker
docker compose up -d --build
```

If the update includes new Python modules (like `numeric_change.py`), ensure they are listed in `Dockerfile.backend`'s COPY instructions. The current backend image includes:

```
config.py, store.py, run_pipeline.py, advisor_query.py,
document_pull.py, extract_clean.py, embeddings.py, similarity.py,
attention_proxy.py, abnormal_returns.py, las.py, numeric_change.py
```

## Tearing Down

```bash
cd deploy/terraform
terraform destroy   # type "yes" to confirm
```

This removes the EC2 instance, Elastic IP, security group, IAM role, and SSM parameter.

## Local Docker Testing

You can test the Docker setup locally before deploying to AWS:

```bash
# From the project root, create a .env file with your API key
echo "OPENAI_API_KEY=sk-..." > .env

# Build and start
cd deploy/docker
docker compose up -d --build

# Open http://localhost in your browser

# Run the pipeline
docker compose --profile pipeline run --rm pipeline --ciks 320193

# Stop
docker compose down
```

## Adding HTTPS (Optional)

After deployment, you can add free TLS with Let's Encrypt:

```bash
ssh -i ~/.ssh/<key_name>.pem ec2-user@<ELASTIC_IP>

# Install certbot
sudo dnf install -y certbot python3-certbot-nginx

# Obtain certificate (replace with your domain)
sudo certbot --nginx -d yourdomain.com
```

This requires a domain name pointed at your Elastic IP.

## Key Configuration

| Setting | File | Default | Description |
| --- | --- | --- | --- |
| `PIPELINE_VERSION` | `config.py` | `1.3` | Bump to force reprocessing of all filings |
| `NUMERIC_CHANGE_ALPHA` | `config.py` | `0.7` | Blend weight: 0.7 text similarity + 0.3 numerical divergence |
| `LAS_WEIGHTS` | `config.py` | `{w_change: 0.50, w_attention: 0.25, w_car: 0.25}` | Weights for the LAS formula |
| `SECTION_WEIGHTS` | `config.py` | MD&A 0.30, Risk Factors 0.25, ... | Per-section importance for weighted change intensity |
| `DATABASE_URL` | `.env` / compose | `sqlite:///data/las_store.db` | SQLite locally, PostgreSQL in Docker |
