# AWS Deployment Guide

> **Architecture:** Single EC2 Spot instance · Nginx · Docker Compose · RDS PostgreSQL · S3 · Qdrant Cloud · Bedrock
>
> See also: [aws-cost.md](aws-cost.md) · [domain-and-https.md](domain-and-https.md) · [security.md](security.md)

---

## Architecture overview

```
Internet ──► EC2 Spot t4g.small (Public IP / Custom Domain)
                  │
               Nginx :80/:443
             ┌────┴──────┐
             ▼           ▼
          :3000        :8000
         Next.js      FastAPI
         (frontend)    (API)
                         │
        ┌────────────────┼───────────────┐
        ▼                ▼               ▼
    Bedrock          Qdrant Cloud    RDS PostgreSQL
    (LLM)            (vectors)       (user data)
                              S3 (tax docs)

ECR: single repo, two image tags
  <repo>:api-latest        ← FastAPI
  <repo>:frontend-latest   ← Next.js

Secrets Manager (all resolved at EC2 boot):
  ai-tax-agent-dev/db-credentials    ← DB URL
  ai-tax-agent-dev/qdrant-api-key    ← Qdrant key
  ai-tax-agent-dev/oidc-credentials  ← OIDC secret (optional)
```

---

## Prerequisites

- AWS account with Bedrock model access enabled for `ap-south-1`
- AWS CLI configured (`aws configure` or `aws sso login`)
- Terraform ≥ 1.7: `terraform -version`
- Docker installed and running
- An EC2 key pair in `ap-south-1` (needed for SSH; SSM Session Manager works without it)

---

## Step 1 — Create infrastructure (Terraform)

```bash
cd infra/terraform/environments/dev

# First time only
terraform init

# Review and edit variables
cp dev.tfvars.example dev.tfvars
# Edit dev.tfvars:
#   key_name      = "your-ec2-keypair"
#   db_username   = "taxly_user"
#   db_password   = "StrongPass123!"   ← never commit this file
#   alarm_email   = "you@example.com"

# Validate
terraform fmt -recursive && terraform validate

# Review what will be created (READ before applying)
terraform plan -var-file="dev.tfvars"
```

**Resources created and approximate costs (ap-south-1):**

| Resource | Size | Est. cost/month |
|----------|------|----------------|
| EC2 Spot t4g.small | 2 vCPU / 2 GB | ~$5–8 |
| RDS db.t4g.micro | 1 vCPU / 1 GB | ~$12–15 |
| S3 + ECR storage | < 5 GB | ~$1 |
| CloudWatch logs (7d) | minimal | ~$1 |
| **Total** | | **~$20–25/month** |

> ⚠️ Spot instances can be interrupted. RDS data is persistent.

```bash
# Apply after reviewing the plan
terraform apply -var-file="dev.tfvars"

# Save key outputs
terraform output
```

---

## Step 2 — Populate secrets

Terraform creates the secret **containers**. You fill in the values:

```bash
# Interactive helper (prompts for Qdrant key and OIDC secret)
./scripts/populate_secrets.sh

# Or manually:
REGION=ap-south-1

# Verify DB credentials (Terraform populates this from dev.tfvars automatically)
aws secretsmanager get-secret-value \
    --secret-id ai-tax-agent-dev/db-credentials --region $REGION

# Qdrant Cloud API key
aws secretsmanager put-secret-value \
    --secret-id ai-tax-agent-dev/qdrant-api-key --region $REGION \
    --secret-string '{"api_key":"<your-qdrant-key>","url":"https://xyz.qdrant.io"}'

# OIDC client secret (optional — skip if using JWT dev auth)
aws secretsmanager put-secret-value \
    --secret-id ai-tax-agent-dev/oidc-credentials --region $REGION \
    --secret-string '{"client_secret":"<your-oidc-secret>"}'
```

---

## Step 3 — Build and push Docker images to ECR

```bash
# All-in-one script — builds both images and pushes to ECR
./scripts/deploy.sh

# Or step-by-step:
REGION=ap-south-1
ECR_REPO=$(terraform -chdir=infra/terraform/environments/dev output -raw ecr_repository_url)
ECR_REGISTRY="${ECR_REPO%%/*}"

aws ecr get-login-password --region $REGION \
    | docker login --username AWS --password-stdin $ECR_REGISTRY

# API (backend)  — tag: api-latest
docker build -t taxly-api:build -f Dockerfile .
docker tag taxly-api:build $ECR_REPO:api-latest
docker push $ECR_REPO:api-latest

# Frontend — tag: frontend-latest
EC2_IP=$(terraform -chdir=infra/terraform/environments/dev output -raw ec2_public_ip)
docker build \
    --build-arg NEXT_PUBLIC_API_BASE_URL="http://$EC2_IP" \
    --build-arg NEXT_PUBLIC_APP_NAME="Taxly" \
    -t taxly-frontend:build frontend/
docker tag taxly-frontend:build $ECR_REPO:frontend-latest
docker push $ECR_REPO:frontend-latest
```

Verify images in ECR:
```bash
aws ecr list-images --repository-name ai-tax-agent-dev --region ap-south-1
```

---

## Step 4 — EC2 boots automatically

The EC2 `user_data` bootstrap script runs on first boot and:

1. Installs Docker, Docker Compose, AWS CLI, Nginx, Python
2. Writes `/usr/local/bin/taxly-fetch-secrets.sh`
3. Writes `/opt/taxly/docker-compose.yml`
4. Enables and starts `taxly-compose.service` (systemd)

The fetch-secrets script (runs before every compose start):
- Uses IMDSv2 to get the region
- Calls `aws secretsmanager get-secret-value` via the IAM instance profile
- Generates a random JWT secret on first boot (`/opt/taxly/.jwt_secret`)
- ECR-logins Docker and writes `/opt/taxly/.env`
- Docker Compose reads `.env` and starts api, frontend, nginx containers

**No secrets are ever stored in Terraform state, user_data, or Docker images.**

---

## Step 5 — Run database migrations

After the stack is up:

```bash
EC2_IP=$(terraform -chdir=infra/terraform/environments/dev output -raw ec2_public_ip)
ssh -i ~/.ssh/your-key.pem ec2-user@$EC2_IP \
    'sudo docker compose -f /opt/taxly/docker-compose.yml exec api alembic upgrade head'
```

---

## Step 6 — Verify deployment

```bash
# All-in-one check script
./scripts/check_deployment.sh

# Manual
EC2_IP=$(terraform -chdir=infra/terraform/environments/dev output -raw ec2_public_ip)
curl http://$EC2_IP/api/v1/health
curl http://$EC2_IP/api/v1/ready
open http://$EC2_IP   # frontend dashboard

# Container status (SSH)
ssh -i ~/.ssh/key.pem ec2-user@$EC2_IP \
    'sudo docker compose -f /opt/taxly/docker-compose.yml ps'

# CloudWatch logs
aws logs tail $(terraform -chdir=infra/terraform/environments/dev output -raw app_log_group) \
    --follow --region ap-south-1
```

---

## Redeploying after code changes

```bash
./scripts/deploy.sh          # builds, pushes, restarts
./scripts/deploy.sh v1.2.0   # with explicit tag
```

---

## Updating secrets

```bash
# Re-run the populate script anytime
./scripts/populate_secrets.sh

# Restart the app to pick up new values
EC2_IP=$(terraform -chdir=infra/terraform/environments/dev output -raw ec2_public_ip)
ssh -i ~/.ssh/key.pem ec2-user@$EC2_IP 'sudo systemctl restart taxly-compose'
```

---

## Recovering from Spot interruption

```bash
cd infra/terraform/environments/dev
terraform apply -var-file="dev.tfvars"   # recreates instance with same user_data
./scripts/deploy.sh                       # push images and restart
```

RDS data is persistent — no data loss.

---

## DNS and HTTPS (optional)

See [domain-and-https.md](domain-and-https.md) for full instructions.

Quick summary:
1. Point your domain A record to the EC2 public IP
2. SSH to EC2, install Certbot, get certificate
3. Update nginx config to add TLS server block
4. Rebuild frontend image with `NEXT_PUBLIC_API_BASE_URL=https://yourdomain.com`
