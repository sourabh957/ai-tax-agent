# Deployment Guide

> See also: [terraform.md](terraform.md) * [production_config.md](production_config.md)

## Local development

```bash
docker compose up --build
# API: http://localhost:8000
# Swagger: http://localhost:8000/docs
# Qdrant UI: http://localhost:6333/dashboard
```

---

## Production flow

```
Git push to master
    |
    v
GitHub Actions (ci.yml)
    +-- Unit tests (342 tests, no paid APIs)
    +-- Terraform fmt + validate
    +-- Docker build check
    |
    v (on success)
GitHub Actions (deploy.yml)
    +-- OIDC auth -> AWS role (no long-lived keys)
    +-- Docker build -> ECR push
    +-- ECS force-new-deployment
    +-- Wait for services-stable
    +-- Auto-rollback on failure
```

---

## ECR push (manual)

```bash
# Get ECR URL from Terraform output
ECR_URL=$(cd infra/terraform/environments/dev && terraform output -raw ecr_repository_url)
REGION=$(cd infra/terraform/environments/dev && terraform output -raw aws_region)

# Authenticate Docker to ECR
aws ecr get-login-password --region $REGION \
    | docker login --username AWS --password-stdin $ECR_URL

# Build and push
docker build -t ai-tax-agent:latest .
docker tag ai-tax-agent:latest $ECR_URL:latest
docker push $ECR_URL:latest

# Or use the deploy script:
./scripts/deploy_ecr.sh v1.0.0
```

---

## ECS deployment (manual)

```bash
# Full deploy with rollback on failure:
./scripts/deploy_ecs.sh v1.0.0 dev

# Or via Terraform (recommended):
cd infra/terraform/environments/dev
terraform apply -var-file=dev.tfvars -var="image_tag=v1.0.0" -var="ecs_desired_count=1"
```

---

## Database migrations in production

Run BEFORE the new ECS task starts receiving traffic:

```bash
# Option 1: ECS Exec (interactive shell in running container)
aws ecs execute-command \
  --cluster ai-tax-agent-dev-cluster \
  --task <TASK_ID> \
  --container ai-tax-agent-api \
  --interactive \
  --command "alembic upgrade head"

# Option 2: One-off ECS task (recommended for production)
aws ecs run-task \
  --cluster ai-tax-agent-dev-cluster \
  --task-definition ai-tax-agent-dev-task \
  --overrides '{
    "containerOverrides": [{
      "name": "ai-tax-agent-api",
      "command": ["alembic", "upgrade", "head"]
    }]
  }'
```

---

## Rollback procedure

```bash
# 1. Find previous task definition revision
aws ecs describe-services \
  --cluster ai-tax-agent-dev-cluster \
  --services ai-tax-agent-dev-service \
  --query "services[0].deployments"

# 2. Roll back to previous revision
aws ecs update-service \
  --cluster ai-tax-agent-dev-cluster \
  --service ai-tax-agent-dev-service \
  --task-definition ai-tax-agent-dev-task:<PREVIOUS_REVISION> \
  --force-new-deployment

# 3. Wait for stability
aws ecs wait services-stable \
  --cluster ai-tax-agent-dev-cluster \
  --services ai-tax-agent-dev-service
```

---

## Verifying a deployment

```bash
# Check task status
aws ecs describe-services \
  --cluster ai-tax-agent-dev-cluster \
  --services ai-tax-agent-dev-service \
  --query "services[0].{running:runningCount,desired:desiredCount,pending:pendingCount}"

# Tail CloudWatch logs
aws logs tail /ecs/ai-tax-agent-dev --follow --region ap-south-1

# Health check (if you have the task IP)
curl http://<TASK_PUBLIC_IP>:8000/api/v1/health

# Config check (via ECS Exec)
aws ecs execute-command \
  --cluster ai-tax-agent-dev-cluster \
  --task <TASK_ID> \
  --interactive \
  --command "python -m app.core.config_check"
```

---

## Cost management

```bash
# Stop all ECS tasks when not in use (zero Fargate cost)
cd infra/terraform/environments/dev
terraform apply -var-file=dev.tfvars -var="ecs_desired_count=0"

# Start one task for testing
terraform apply -var-file=dev.tfvars -var="ecs_desired_count=1"
```