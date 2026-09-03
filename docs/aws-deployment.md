# AWS Deployment Guide

> **Architecture:** Single EC2 Spot instance · Nginx · Docker · RDS PostgreSQL · S3 · Qdrant Cloud · Bedrock
>
> See also: [aws-cost.md](aws-cost.md) · [domain-and-https.md](domain-and-https.md) · [security.md](security.md)

---

## Architecture overview

```
Internet → Custom Domain (DNS) → EC2 Spot (t4g.small)
                                      │
                                   Nginx
                               ┌────┴─────┐
                               │          │
                            :3000      :8000
                           Next.js    FastAPI
                                         │
                          ┌──────────────┼──────────────┐
                          │              │              │
                       Bedrock       Qdrant Cloud    RDS PostgreSQL
                        (LLM)       (vectors)        (user data)
                          └──────────────┘
                                 S3
                            (tax documents)
```

---

## Prerequisites

- AWS account with Bedrock model access enabled
- AWS CLI configured: `aws configure`
- Terraform ≥ 1.7 installed
- Docker installed and running
- A registered domain name (purchase separately)
- EC2 SSH key pair created

---

## Step 1: Create infrastructure (Terraform)

```bash
cd infra/terraform/environments/dev

# Copy and fill in variables
cp dev.tfvars.example dev.tfvars
# Edit dev.tfvars:
#   key_name = "your-ec2-keypair"
#   domain_name = "yourdomain.com"
#   db_username = "taxly_user"
#   db_password = "strong-password-here"

# Review what will be created
terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="dev.tfvars"

# ⚠️ Review the plan and estimated costs before applying
# After review:
terraform apply -var-file="dev.tfvars"

# Save outputs
terraform output
```

**Resources created:**
- VPC + public/private subnets + Internet Gateway
- Security groups (EC2: 80/443/22; RDS: 5432 from EC2 only)
- IAM instance profile (Bedrock + S3 + CloudWatch + Secrets Manager)
- EC2 Spot instance (t4g.small) — auto-bootstrapped via user_data
- RDS PostgreSQL (db.t4g.micro) — private subnet
- S3 bucket (encrypted, private)
- ECR repositories (backend + frontend)
- CloudWatch log group

---

## Step 2: Push Docker images to ECR

```bash
# Get ECR URLs from Terraform
ECR_BACKEND=$(terraform -chdir=infra/terraform/environments/dev output -raw ecr_backend_repository_url)
ECR_FRONTEND=$(terraform -chdir=infra/terraform/environments/dev output -raw ecr_frontend_repository_url)
REGION=$(terraform -chdir=infra/terraform/environments/dev output -raw aws_region)

# Authenticate Docker to ECR
aws ecr get-login-password --region $REGION \
    | docker login --username AWS --password-stdin ${ECR_BACKEND%%/*}

# Build and push backend
docker build -t taxly-backend:latest .
docker tag taxly-backend:latest $ECR_BACKEND:latest
docker push $ECR_BACKEND:latest

# Build and push frontend
docker build \
    --build-arg NEXT_PUBLIC_API_BASE_URL=https://yourdomain.com \
    -t taxly-frontend:latest frontend/
docker tag taxly-frontend:latest $ECR_FRONTEND:latest
docker push $ECR_FRONTEND:latest

# Or use the all-in-one deploy script:
./scripts/deploy.sh v1.0.0
```

---

## Step 3: Configure the EC2 instance

SSH into the EC2 instance:

```bash
EC2_IP=$(terraform -chdir=infra/terraform/environments/dev output -raw ec2_public_ip)
ssh -i ~/.ssh/your-key.pem ec2-user@$EC2_IP
```

Create the application environment file:

```bash
sudo mkdir -p /opt/taxly
sudo cat > /opt/taxly/.env << 'EOF'
# Copy from your actual values — NEVER commit this file
AWS_REGION=ap-south-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
S3_BUCKET_NAME=your-bucket-name
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION=tax_rules
DATABASE_URL=postgresql+asyncpg://user:pass@rds-endpoint/taxly
DOMAIN_NAME=yourdomain.com
ECR_BACKEND_URI=account.dkr.ecr.region.amazonaws.com/taxly-backend
ECR_FRONTEND_URI=account.dkr.ecr.region.amazonaws.com/taxly-frontend
IMAGE_TAG=latest
CORS_ALLOWED_ORIGINS=https://yourdomain.com
EOF

# Copy docker-compose.prod.yml to the instance
scp -i ~/.ssh/your-key.pem docker-compose.prod.yml ec2-user@$EC2_IP:/opt/taxly/

# Start the application
cd /opt/taxly
aws ecr get-login-password --region ap-south-1 \
    | docker login --username AWS --password-stdin account.dkr.ecr.region.amazonaws.com
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## Step 4: Run database migrations

```bash
# On EC2
docker exec taxly-backend alembic upgrade head
```

---

## Step 5: Configure DNS and HTTPS

See [domain-and-https.md](domain-and-https.md) for full instructions.

Quick summary:
1. Point your domain A record to `EC2_IP`
2. Install Certbot: `sudo snap install certbot --classic`
3. Configure Nginx: `sudo cp /opt/taxly/nginx.conf /etc/nginx/sites-available/taxly`
4. Replace `DOMAIN_NAME` in the config
5. Get certificate: `sudo certbot --nginx -d yourdomain.com`
6. Reload Nginx: `sudo nginx -s reload`

---

## Verify deployment

```bash
# Health checks
curl https://yourdomain.com/api/v1/health
curl https://yourdomain.com/api/v1/ready

# Check containers
docker compose -f /opt/taxly/docker-compose.prod.yml ps

# Tail logs
docker logs taxly-backend --follow
docker logs taxly-frontend --follow

# CloudWatch logs
aws logs tail /ec2/taxly-prod --follow --region ap-south-1
```

---

## Recovering from Spot interruption

EC2 Spot instances can be interrupted. Recovery:

```bash
# Terraform recreates the instance automatically
# (Spot replacement or explicit terraform apply)
cd infra/terraform/environments/dev
terraform apply -var-file="dev.tfvars"

# New instance bootstraps automatically (Docker, Nginx installed via user_data)
# Deploy latest images:
./scripts/deploy.sh latest

# Reconnect to RDS (no data loss — RDS is persistent)
```

---

## Migration path (future)

When traffic grows, migrate to ECS/Fargate:

```
Current:    EC2 Spot → Nginx → Docker containers
Future:     ALB → ECS Fargate → (separate frontend/backend services)
```

The application is stateless and containerized — migration is possible without data loss.
See `infra/terraform/modules/ecs/` for the ECS module (already built, not deployed yet).
