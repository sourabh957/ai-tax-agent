#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full deployment to EC2 Spot instance
#
# Usage:
#   ./scripts/deploy.sh [IMAGE_TAG]
#
# Prerequisites:
#   - AWS CLI configured with EC2 instance profile or deployment role
#   - Terraform applied (EC2, ECR, RDS, S3 infrastructure exists)
#   - SSH key configured for EC2 access
#   - ECR_BACKEND_URI and ECR_FRONTEND_URI exported or in .env
# =============================================================================
set -euo pipefail

IMAGE_TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
TERRAFORM_DIR="infra/terraform/environments/dev"
SCRIPTS_DIR="$(dirname "$0")"

echo "==> Taxly Deploy [tag=${IMAGE_TAG}]"
echo ""

# ── 1. Verify AWS identity ────────────────────────────────────────────────────
echo "==> Verifying AWS identity..."
aws sts get-caller-identity
echo ""

# ── 2. Get Terraform outputs ──────────────────────────────────────────────────
echo "==> Reading infrastructure outputs..."
EC2_IP=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ec2_public_ip 2>/dev/null) || {
    echo "ERROR: Could not read ec2_public_ip. Run terraform apply first."
    exit 1
}
REGION=$(terraform -chdir="${TERRAFORM_DIR}" output -raw aws_region 2>/dev/null || echo "ap-south-1")
ECR_BACKEND=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecr_backend_repository_url 2>/dev/null) || ECR_BACKEND=""
ECR_FRONTEND=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecr_frontend_repository_url 2>/dev/null) || ECR_FRONTEND=""

echo "  EC2 IP:      ${EC2_IP}"
echo "  Region:      ${REGION}"
echo "  Backend ECR: ${ECR_BACKEND}"
echo "  Frontend ECR:${ECR_FRONTEND}"
echo ""

# ── 3. ECR login ──────────────────────────────────────────────────────────────
echo "==> Authenticating Docker to ECR..."
aws ecr get-login-password --region "${REGION}" \
    | docker login --username AWS --password-stdin "${ECR_BACKEND%%/*}"
echo ""

# ── 4. Build and push backend ─────────────────────────────────────────────────
echo "==> Building backend image..."
docker build -t taxly-backend:${IMAGE_TAG} -f Dockerfile .
docker tag taxly-backend:${IMAGE_TAG} ${ECR_BACKEND}:${IMAGE_TAG}
docker tag taxly-backend:${IMAGE_TAG} ${ECR_BACKEND}:latest
docker push ${ECR_BACKEND}:${IMAGE_TAG}
docker push ${ECR_BACKEND}:latest
echo "  Backend pushed: ${ECR_BACKEND}:${IMAGE_TAG}"
echo ""

# ── 5. Build and push frontend ────────────────────────────────────────────────
echo "==> Building frontend image..."
docker build \
    --build-arg NEXT_PUBLIC_API_BASE_URL="https://${DOMAIN_NAME:-yourdomain.com}" \
    --build-arg NEXT_PUBLIC_APP_NAME="Taxly" \
    -t taxly-frontend:${IMAGE_TAG} \
    -f frontend/Dockerfile \
    frontend/
docker tag taxly-frontend:${IMAGE_TAG} ${ECR_FRONTEND}:${IMAGE_TAG}
docker tag taxly-frontend:${IMAGE_TAG} ${ECR_FRONTEND}:latest
docker push ${ECR_FRONTEND}:${IMAGE_TAG}
docker push ${ECR_FRONTEND}:latest
echo "  Frontend pushed: ${ECR_FRONTEND}:${IMAGE_TAG}"
echo ""

# ── 6. Deploy to EC2 via SSH ─────────────────────────────────────────────────
KEY_FILE="${SSH_KEY_FILE:-~/.ssh/taxly-ec2.pem}"
SSH_USER="${SSH_USER:-ec2-user}"

echo "==> Deploying to EC2 [${EC2_IP}]..."
ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=no "${SSH_USER}@${EC2_IP}" << REMOTE
    set -e

    # Authenticate EC2 Docker to ECR (using instance profile — no keys needed)
    aws ecr get-login-password --region ${REGION} \
        | docker login --username AWS --password-stdin ${ECR_BACKEND%%/*}

    # Pull latest images
    docker pull ${ECR_BACKEND}:${IMAGE_TAG}
    docker pull ${ECR_FRONTEND}:${IMAGE_TAG}

    # Update image tags in compose env
    cd /opt/taxly
    sed -i "s|IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|g" .env 2>/dev/null || true
    echo "IMAGE_TAG=${IMAGE_TAG}" >> .env

    # Restart with zero-downtime (backend first, then frontend)
    docker compose -f docker-compose.prod.yml up -d --no-deps backend
    sleep 10
    curl -sf http://localhost:8000/api/v1/health || { echo "Backend health check failed"; exit 1; }

    docker compose -f docker-compose.prod.yml up -d --no-deps frontend
    sleep 5
    curl -sf http://localhost:3000 || { echo "Frontend health check failed"; exit 1; }

    echo "Deploy successful: tag=${IMAGE_TAG}"
REMOTE

echo ""
echo "==> Deployment complete!"
echo "    Application: https://${DOMAIN_NAME:-your-domain}"
echo "    Backend:     https://${DOMAIN_NAME:-your-domain}/api/v1/health"
echo "    Image tag:   ${IMAGE_TAG}"
